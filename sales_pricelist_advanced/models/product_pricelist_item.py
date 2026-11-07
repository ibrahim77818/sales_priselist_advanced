# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.fields import Domain

TARGET_ANY = '2_any'
TARGET_UOM = '1_uom'

PRODUCT_SCOPES = ('1_product', '0_product_variant')
# Odoo 20 rule types computed from a base price (former "formula" rules)
FORMULA_TYPES = ('discount', 'markup')


def uom_root(uom):
    """Reference unit at the top of the UoM tree (Odoo 19 has no UoM categories:
    units are related through ``relative_uom_id``). Two units can be converted
    into each other only when they share the same root."""
    if not uom:
        return False
    if uom.parent_path:
        return int(uom.parent_path.split('/')[0])
    while uom.relative_uom_id:
        uom = uom.relative_uom_id
    return uom.id


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'
    # Unit/packaging rules win over generic rules of the same scope.
    # Scope (applied_on) keeps precedence so the standard hierarchy is preserved.
    _order = "applied_on, asp_target, min_quantity desc, categ_id desc, id desc"

    # Odoo 20 defines uom_id ("Packaging") on rules and matches it against the
    # line unit; this app makes the rule amounts per that unit / package.
    uom_id = fields.Many2one(
        string="Unit / Packaging",
        ondelete='cascade',
        index=True,
        help="Apply this rule only when the product is sold in this unit or packaging.\n"
             "Fixed price, extra fee and margins are then expressed per this unit / package, "
             "and the minimum quantity is counted in this unit / in packages.")
    asp_uom_name = fields.Char(related='uom_id.name', string="Rule Unit Name")
    asp_target = fields.Selection(
        selection=[
            (TARGET_UOM, "Unit / Packaging"),
            (TARGET_ANY, "Any Unit"),
        ],
        string="Sold As",
        compute='_compute_asp_target',
        store=True,
        index=True,
        help="Technical field used to give unit / packaging rules priority over generic ones.")
    asp_allowed_uom_ids = fields.Many2many(
        comodel_name='uom.uom',
        string="Allowed Units",
        compute='_compute_asp_allowed_uom_ids')

    # Percentage extra fee (formula rules), added at the same step as the
    # fixed extra fee: after discount and rounding, before the margins.
    price_surcharge_percent = fields.Float(
        string="Extra Fee (%)",
        digits=(16, 2),
        default=0.0,
        help="Extra fee expressed as a percentage, added after the discount and rounding "
             "(like the fixed extra fee) and before the margins are applied.\n"
             "Use a negative value for a percentage rebate.")
    price_surcharge_percent_base = fields.Selection(
        selection=[
            ('base', "Base Price"),
            ('discounted', "Discounted Price"),
        ],
        string="Extra Fee (%) On",
        default='base',
        required=True,
        help="Amount the percentage extra fee is computed on:\n"
             "Base Price: the price the rule is based on (sales price, cost or other pricelist).\n"
             "Discounted Price: the price after the rule discount and rounding.")

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('uom_id')
    def _compute_asp_target(self):
        for item in self:
            item.asp_target = TARGET_UOM if item.uom_id else TARGET_ANY

    @api.depends('applied_on', 'product_id', 'product_tmpl_id', 'product_id.extra_uom_ids',
                 'product_tmpl_id.uom_id', 'product_tmpl_id.uom_ids')
    def _compute_asp_allowed_uom_ids(self):
        all_uoms = None
        for item in self:
            product = item._asp_scope_product()
            if product:
                # Same choice as on sales order lines: the product unit and its packagings
                # (Odoo 20 also has variant-specific packagings).
                uoms = product.uom_id | product.uom_ids
                if product._name == 'product.product':
                    uoms |= product.extra_uom_ids
                item.asp_allowed_uom_ids = uoms
            else:
                if all_uoms is None:
                    all_uoms = self.env['uom.uom'].search([])
                item.asp_allowed_uom_ids = all_uoms

    @api.depends('uom_id', 'uom_id.name')
    def _compute_name(self):
        super()._compute_name()
        for item in self:
            unit_label = item._asp_unit_label()
            if unit_label:
                item.name = _("%(name)s (%(unit)s)", name=item.name, unit=unit_label)

    @api.depends('uom_id', 'uom_id.name', 'price_surcharge_percent', 'price_surcharge_percent_base')
    def _compute_price_label(self):
        super()._compute_price_label()
        for item in self:
            if item.compute_price in FORMULA_TYPES and item.price_surcharge_percent:
                item.price = _(
                    "%(price)s and %(fee)s %% extra fee on the %(basis)s",
                    price=item.price.strip(), fee=item.price_surcharge_percent,
                    basis=item._asp_fee_basis_label().lower())
            unit_label = item._asp_unit_label()
            if unit_label and item.compute_price == 'fixed':
                item.price = _("%(price)s per %(unit)s", price=item.price, unit=unit_label)

    @api.depends('uom_id', 'price_surcharge_percent', 'price_surcharge_percent_base',
                 'price_min_margin', 'price_max_margin', 'price_markup')
    def _compute_rule_tip(self):
        super()._compute_rule_tip()
        for item in self:
            if item.compute_price in FORMULA_TYPES and item.price_surcharge_percent:
                item.rule_tip = item._asp_percent_fee_rule_tip()
            unit_label = item._asp_unit_label()
            if item.rule_tip and unit_label:
                item.rule_tip = "%s\n%s" % (
                    item.rule_tip,
                    _("Base price, extra fee and margins are computed per %s.", unit_label),
                )

    @api.depends('price_surcharge_percent')
    def _compute_is_plain_discount(self):
        # A percentage fee makes the result differ from "price - discount %":
        # Odoo must not show it as a plain discount on order lines.
        super()._compute_is_plain_discount()
        for item in self:
            if item.price_surcharge_percent:
                item.is_plain_discount = False

    def _search_is_plain_discount(self, operator, value):
        domain = super()._search_is_plain_discount(operator, value)
        if operator == 'in':
            return domain & Domain('price_surcharge_percent', '=', 0)
        return domain | Domain('price_surcharge_percent', '!=', 0)

    # ------------------------------------------------------------------
    # Constraints / onchanges / CRUD
    # ------------------------------------------------------------------

    @api.constrains('uom_id', 'applied_on', 'product_id', 'product_tmpl_id')
    def _check_asp_targets(self):
        for item in self:
            if not item.uom_id:
                continue
            product = item._asp_scope_product()
            if product and uom_root(product.uom_id) != uom_root(item.uom_id):
                raise ValidationError(_(
                    "Pricelist rule \"%(rule)s\": the unit \"%(uom)s\" cannot be converted into the "
                    "product unit \"%(product_uom)s\".",
                    rule=item.display_name, uom=item.uom_id.display_name,
                    product_uom=product.uom_id.display_name))

    @api.constrains('price_min_margin', 'price_max_margin')
    def _check_margin(self):
        # Standard check rejects a minimum margin alone (max 0 = "no maximum"
        # for the engine, but 0 < min for the constraint). Compare only when
        # a maximum margin is actually set.
        if any(item.price_max_margin and item.price_min_margin > item.price_max_margin for item in self):
            raise ValidationError(_('The minimum margin should be lower than the maximum margin.'))

    @api.onchange('product_id', 'product_tmpl_id', 'categ_id')
    def _asp_onchange_scope(self):
        for item in self:
            if item.uom_id and item.uom_id not in item.asp_allowed_uom_ids:
                item.uom_id = False

    @api.onchange('compute_price')
    def _onchange_compute_price(self):
        res = super()._onchange_compute_price()
        for item in self:
            if item.compute_price not in FORMULA_TYPES:
                item.price_surcharge_percent = 0.0
                item.price_surcharge_percent_base = 'base'
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Empty cells of an import come as False and would override the
            # defaults of these required fields: let the defaults apply.
            for fname in ('compute_price', 'base', 'price_surcharge_percent_base'):
                if fname in vals and not vals[fname]:
                    del vals[fname]
            self._asp_sanitize_markup(vals)
        return super().create(vals_list)

    def write(self, vals):
        # Required selections cannot be emptied (empty import cells): keep the current value.
        for fname in ('compute_price', 'base', 'price_surcharge_percent_base'):
            if fname in vals and not vals[fname]:
                vals = {k: v for k, v in vals.items() if k != fname}
        if 'price_markup' in vals:
            vals = self._asp_sanitize_markup(dict(vals))
        return super().write(vals)

    @api.model
    def _asp_sanitize_markup(self, vals):
        """Imports send every column of the file: an empty 'price_markup' cell
        (0) would overwrite the discount of a Discount rule through the markup
        inverse (price_discount = -price_markup). Only a filled markup counts."""
        if 'price_markup' in vals:
            markup = vals.pop('price_markup')
            if markup:
                vals['price_discount'] = -markup
        return vals

    @api.model
    def get_import_templates(self):
        return [
            {
                'label': _("Pricelist rules - Fixed prices (product, unit, packaging)"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelist_rules_basic.xlsx',
            },
            {
                'label': _("Pricelist rules - All rule types (discounts, surcharges)"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelist_rules_advanced.xlsx',
            },
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _asp_scope_product(self):
        """Product (template or variant) the rule is scoped to, empty for category/global rules."""
        self.ensure_one()
        if self.applied_on == '0_product_variant' and self.product_id:
            return self.product_id
        if self.applied_on == '1_product' and self.product_tmpl_id:
            return self.product_tmpl_id
        # Odoo 20 computes applied_on from the category / product fields.
        return self.env['product.template']

    def _asp_unit_label(self):
        self.ensure_one()
        return self.uom_id.name or ''

    def _asp_is_targeted(self):
        return bool(self) and self.asp_target == TARGET_UOM

    def _asp_has_percent_fee(self):
        return bool(self) and self.compute_price in FORMULA_TYPES and bool(self.price_surcharge_percent)

    def _asp_fee_basis_label(self):
        self.ensure_one()
        selection = dict(self._fields['price_surcharge_percent_base']._description_selection(self.env))
        return selection.get(self.price_surcharge_percent_base or 'base', '')

    def _asp_apply_formula(self, base_price, convert=None):
        """Odoo 20 discount / markup formula, extended with the percentage extra fee.

        Same order as the standard engine: discount -> rounding -> extra fees
        -> min/max margins. ``base_price`` is expressed in the unit the result
        is wanted in; ``convert`` converts amounts the rule stores per product
        UoM (fixed extra fee and margins) into that unit.
        """
        self.ensure_one()
        convert = convert or (lambda amount: amount)
        price_limit = base_price
        # A markup is stored as a negative discount (price_markup = -price_discount).
        price = (base_price - (base_price * (self.price_discount / 100))) or 0.0
        if self.price_round:
            price = tools.float_round(price, precision_rounding=self.price_round)
        discounted_price = price
        if self.price_surcharge:
            price += convert(self.price_surcharge)
        if self.price_surcharge_percent:
            fee_basis = discounted_price if self.price_surcharge_percent_base == 'discounted' else base_price
            price += fee_basis * self.price_surcharge_percent / 100
        if self.price_min_margin:
            price = max(price, price_limit + convert(self.price_min_margin))
        if self.price_max_margin:
            price = min(price, price_limit + convert(self.price_max_margin))
        return price

    def _asp_percent_fee_rule_tip(self):
        self.ensure_one()
        base_selection = dict(self._fields['base']._description_selection(self.env))
        example = self._asp_apply_formula(100.0)
        discount_type, discount = self._get_displayed_discount(self)
        return _(
            "%(base)s with a %(discount)s %% %(discount_type)s, %(surcharge)s extra fee and %(fee)s %% "
            "extra fee on the %(basis)s\nExample: %(amount)s → %(total)s",
            base=base_selection.get(self.base, ''),
            discount=discount,
            discount_type=discount_type,
            surcharge=tools.format_amount(self.env, self.price_surcharge, self.currency_id),
            fee=self.price_surcharge_percent,
            basis=self._asp_fee_basis_label().lower(),
            amount=tools.format_amount(self.env, 100, self.currency_id),
            total=tools.format_amount(self.env, example, self.currency_id),
        )

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------

    # Odoo 20 matches the rule unit itself (_is_applicable_for and the rule
    # domain receive the requested unit) and counts the minimum quantity in
    # that unit. Only the price differs: core keeps fixed price, extra fee and
    # margins per product unit, this app reads them per rule unit / package.

    def _compute_price(self, product, quantity, uom, **kwargs):
        if len(self) != 1 or not (self._asp_is_targeted() or self._asp_has_percent_fee()):
            return super()._compute_price(product, quantity, uom, **kwargs)
        product.ensure_one()
        uom = uom or product._get_main_uom()
        uom.ensure_one()

        if not self._asp_is_targeted():
            # Generic rule with a percentage fee: standard formula (amounts per
            # product unit, converted to `uom`) plus the fee.
            product_uom = product.uom_id
            convert = (lambda p: product_uom._compute_price(p, uom)) if product_uom != uom else None
            base_price = self._compute_base_price(product, quantity, uom, **kwargs)
            return self._asp_apply_formula(base_price, convert)

        rule_uom = self.uom_id
        if uom_root(rule_uom) != uom_root(uom):
            # Should never happen for a matching rule; stay safe and standard.
            return super()._compute_price(product, quantity, uom, **kwargs)

        def to_requested_uom(price_per_rule_unit):
            return rule_uom._compute_price(price_per_rule_unit, uom)

        if self.compute_price == 'fixed':
            # Same attribute extra prices as the standard fixed price.
            if self.applied_on == '0_product_variant':
                extra_price = self.env.context.get('no_variant_attributes_price_extra', 0)
            else:
                extra_price = product._get_attributes_extra_price()
            extra_price = product.uom_id._compute_price(extra_price, uom)
            extra_price = self._convert_price(extra_price, product.currency_id, **kwargs)
            return to_requested_uom(self.fixed_price) + extra_price

        # Base price for ONE rule unit (one package / one unit of the rule).
        qty_in_rule_uom = uom._compute_quantity(quantity, rule_uom, round=False)
        base_price = self._compute_base_price(product, qty_in_rule_uom, rule_uom, **kwargs)
        if self.compute_price in FORMULA_TYPES:
            # Amounts of a unit / packaging rule are already per rule unit.
            price = self._asp_apply_formula(base_price)
        else:
            price = base_price
        return to_requested_uom(price)
