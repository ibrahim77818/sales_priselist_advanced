# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

# Context keys set by the pricing engine (see product.pricelist._compute_price_rule)
CTX_ENGINE = 'asp_pricing'
CTX_UOM = 'asp_uom_id'
CTX_PACKAGING = 'asp_packaging_id'

TARGET_ANY = '2_any'
TARGET_UOM = '1_uom'
TARGET_PACKAGING = '0_packaging'

PRODUCT_SCOPES = ('1_product', '0_product_variant')


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'
    # Targeted rules (packaging > UoM) win over generic rules of the same scope.
    # Scope (applied_on) keeps precedence so the standard hierarchy is preserved.
    _order = "applied_on, asp_target, min_quantity desc, categ_id desc, id desc"

    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string="Unit of Measure",
        ondelete='restrict',
        index=True,
        help="Apply this rule only when the product is sold in this unit of measure.\n"
             "Fixed price, extra fee and margins are then expressed per this unit, "
             "and the minimum quantity is counted in this unit.")
    packaging_id = fields.Many2one(
        comodel_name='product.packaging',
        string="Packaging",
        ondelete='cascade',
        index=True,
        check_company=True,
        help="Apply this rule only when the sales order line uses this packaging.\n"
             "Fixed price, extra fee and margins are then expressed per package, "
             "and the minimum quantity is counted in packages.")
    asp_target = fields.Selection(
        selection=[
            (TARGET_PACKAGING, "Packaging"),
            (TARGET_UOM, "Unit of Measure"),
            (TARGET_ANY, "Any Unit"),
        ],
        string="Sold As",
        compute='_compute_asp_target',
        store=True,
        index=True,
        help="Technical field used to give targeted rules priority over generic ones.")
    asp_allowed_uom_ids = fields.Many2many(
        comodel_name='uom.uom',
        string="Allowed Units of Measure",
        compute='_compute_asp_allowed_targets')
    asp_allowed_packaging_ids = fields.Many2many(
        comodel_name='product.packaging',
        string="Allowed Packagings",
        compute='_compute_asp_allowed_targets')

    # Import helper: packaging names are not unique across products, so they
    # are resolved within the rule's own product instead of globally.
    packaging_name = fields.Char(
        string="Packaging Name",
        compute='_compute_packaging_name',
        inverse='_inverse_packaging_name',
        help="Name of a packaging of the rule's product. Used by imports: the packaging is searched "
             "among the packagings of that product only.")

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

    @api.depends('uom_id', 'packaging_id')
    def _compute_asp_target(self):
        for item in self:
            if item.packaging_id:
                item.asp_target = TARGET_PACKAGING
            elif item.uom_id:
                item.asp_target = TARGET_UOM
            else:
                item.asp_target = TARGET_ANY

    @api.depends('packaging_id.name')
    def _compute_packaging_name(self):
        for item in self:
            item.packaging_name = item.packaging_id.name or False

    def _inverse_packaging_name(self):
        for item in self:
            name = (item.packaging_name or '').strip()
            if not name:
                item.packaging_id = False
                continue
            if item.packaging_id.name == name:
                continue
            if item.product_id:
                candidates, product_name = item.product_id.packaging_ids, item.product_id.display_name
            elif item.product_tmpl_id:
                candidates = item.product_tmpl_id.with_context(active_test=False).product_variant_ids.packaging_ids
                product_name = item.product_tmpl_id.display_name
            else:
                raise ValidationError(_(
                    "Pricelist rule \"%s\": a packaging-specific rule must apply on a product "
                    "or a product variant.", item.display_name))
            match = candidates.filtered(lambda p: p.name == name) \
                or candidates.filtered(lambda p: (p.name or '').casefold() == name.casefold())
            if not match:
                raise ValidationError(_(
                    "Product \"%(product)s\" has no packaging named \"%(packaging)s\".",
                    product=product_name, packaging=name))
            if len(match) > 1:
                raise ValidationError(_(
                    "Several packagings named \"%(packaging)s\" exist for product \"%(product)s\" "
                    "(one per variant): set the product variant on the rule.",
                    product=product_name, packaging=name))
            item.packaging_id = match

    @api.depends('applied_on', 'product_id', 'product_tmpl_id')
    def _compute_asp_allowed_targets(self):
        Uom = self.env['uom.uom']
        Packaging = self.env['product.packaging']
        all_uoms = None
        for item in self:
            product_uom = item._asp_scope_uom()
            if product_uom:
                item.asp_allowed_uom_ids = Uom.search([('category_id', '=', product_uom.category_id.id)])
            else:
                if all_uoms is None:
                    all_uoms = Uom.search([])
                item.asp_allowed_uom_ids = all_uoms
            if item.product_id:
                item.asp_allowed_packaging_ids = Packaging.search([('product_id', '=', item.product_id.id)])
            elif item.product_tmpl_id:
                item.asp_allowed_packaging_ids = Packaging.search(
                    [('product_id.product_tmpl_id', '=', item.product_tmpl_id.id)])
            else:
                item.asp_allowed_packaging_ids = Packaging

    @api.depends('uom_id', 'uom_id.name', 'packaging_id', 'packaging_id.name',
                 'price_surcharge_percent', 'price_surcharge_percent_base')
    def _compute_name_and_price(self):
        super()._compute_name_and_price()
        for item in self:
            if item.compute_price == 'formula' and item.price_surcharge_percent:
                item.price = _(
                    "%(price)s and %(fee)s %% extra fee on the %(basis)s",
                    price=item.price, fee=item.price_surcharge_percent,
                    basis=item._asp_fee_basis_label().lower())
            unit_label = item._asp_unit_label()
            if not unit_label:
                continue
            item.name = _("%(name)s (%(unit)s)", name=item.name, unit=unit_label)
            if item.compute_price == 'fixed':
                item.price = _("%(price)s per %(unit)s", price=item.price, unit=unit_label)

    @api.depends('uom_id', 'packaging_id', 'price_surcharge_percent', 'price_surcharge_percent_base',
                 'price_min_margin', 'price_max_margin')
    def _compute_rule_tip(self):
        super()._compute_rule_tip()
        for item in self:
            if item.compute_price == 'formula' and item.price_surcharge_percent:
                item.rule_tip = item._asp_percent_fee_rule_tip()
            unit_label = item._asp_unit_label()
            if item.rule_tip and unit_label:
                item.rule_tip = "%s\n%s" % (
                    item.rule_tip,
                    _("Base price, extra fee and margins are computed per %s.", unit_label),
                )

    # ------------------------------------------------------------------
    # Constraints / onchanges / CRUD
    # ------------------------------------------------------------------

    @api.constrains('uom_id', 'packaging_id', 'applied_on', 'product_id', 'product_tmpl_id')
    def _check_asp_targets(self):
        for item in self:
            if item.uom_id and item.packaging_id:
                raise ValidationError(_(
                    "Pricelist rule \"%s\": choose either a Unit of Measure or a Packaging, not both.",
                    item.display_name))
            if item.packaging_id:
                packaging = item.packaging_id
                if item.applied_on not in PRODUCT_SCOPES:
                    raise ValidationError(_(
                        "Pricelist rule \"%s\": a packaging-specific rule must apply on a product "
                        "or a product variant.", item.display_name))
                if not packaging.product_id:
                    raise ValidationError(_(
                        "Packaging \"%s\" is not linked to any product and cannot be used in a pricelist rule.",
                        packaging.display_name))
                if float_compare(packaging.qty, 0.0, precision_rounding=packaging.product_uom_id.rounding or 0.0001) <= 0:
                    raise ValidationError(_(
                        "Packaging \"%s\" must contain a strictly positive quantity to be used for pricing.",
                        packaging.display_name))
                if item.applied_on == '0_product_variant' and packaging.product_id != item.product_id:
                    raise ValidationError(_(
                        "Packaging \"%(packaging)s\" does not belong to the product variant \"%(product)s\".",
                        packaging=packaging.display_name, product=item.product_id.display_name))
                if item.applied_on == '1_product' and packaging.product_id.product_tmpl_id != item.product_tmpl_id:
                    raise ValidationError(_(
                        "Packaging \"%(packaging)s\" does not belong to the product \"%(product)s\".",
                        packaging=packaging.display_name, product=item.product_tmpl_id.display_name))
            if item.uom_id:
                product_uom = item._asp_scope_uom()
                if product_uom and product_uom.category_id != item.uom_id.category_id:
                    raise ValidationError(_(
                        "Pricelist rule \"%(rule)s\": the unit of measure \"%(uom)s\" is not in the same "
                        "category as the product unit of measure \"%(product_uom)s\".",
                        rule=item.display_name, uom=item.uom_id.display_name,
                        product_uom=product_uom.display_name))

    @api.constrains('price_min_margin', 'price_max_margin')
    def _check_margin(self):
        # Standard check rejects a minimum margin alone (max 0 = "no maximum"
        # for the engine, but 0 < min for the constraint). Compare only when
        # a maximum margin is actually set.
        if any(item.price_max_margin and item.price_min_margin > item.price_max_margin for item in self):
            raise ValidationError(_('The minimum margin should be lower than the maximum margin.'))

    @api.onchange('applied_on', 'product_id', 'product_tmpl_id')
    def _asp_onchange_scope(self):
        for item in self:
            if item.packaging_id and item.packaging_id not in item.asp_allowed_packaging_ids:
                item.packaging_id = False
            if item.uom_id and item.uom_id not in item.asp_allowed_uom_ids:
                item.uom_id = False

    @api.onchange('compute_price')
    def _onchange_compute_price(self):
        res = super()._onchange_compute_price()
        for item in self:
            if item.compute_price != 'formula':
                item.price_surcharge_percent = 0.0
                item.price_surcharge_percent_base = 'base'
        return res

    @api.onchange('packaging_id')
    def _asp_onchange_packaging_id(self):
        for item in self.filtered('packaging_id'):
            item.uom_id = False

    @api.onchange('uom_id')
    def _asp_onchange_uom_id(self):
        for item in self.filtered('uom_id'):
            item.packaging_id = False

    @api.model
    def _asp_sanitize_vals(self, vals):
        # Mirror the standard "item consistency" rules: a packaging only makes
        # sense on a product/variant scope.
        if vals.get('applied_on') in ('3_global', '2_product_category'):
            vals['packaging_id'] = False
        return vals

    @api.model
    def _asp_resolve_import_packaging(self, vals, product_tmpl=None, product=None):
        """Imports resolve many2one values by name only, and packaging names are
        not unique across products ("Carton of 24" usually exists for many of
        them): the importer then silently picks the first match. Re-resolve the
        packaging by name among the packagings of the rule's own product."""
        if not (self.env.context.get('import_file') and vals.get('packaging_id')):
            return vals
        Packaging = self.env['product.packaging']
        packaging = Packaging.browse(vals['packaging_id'])
        if 'product_id' in vals:
            product = self.env['product.product'].browse(vals['product_id'] or [])
        if 'product_tmpl_id' in vals:
            product_tmpl = self.env['product.template'].browse(vals['product_tmpl_id'] or [])
        if product:
            candidates = product.packaging_ids
        elif product_tmpl:
            candidates = product_tmpl.with_context(active_test=False).product_variant_ids.packaging_ids
        else:
            return vals
        if packaging in candidates:
            return vals
        same_name = candidates.filtered(lambda p: p.name == packaging.name)
        if len(same_name) == 1:
            vals['packaging_id'] = same_name.id
        # 0 or several matches: keep the value, the constraint explains the problem.
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        Product = self.env['product.product']
        for vals in vals_list:
            self._asp_sanitize_vals(vals)
            # Empty cells of an import come as False and would override the
            # defaults of these required fields: let the defaults apply.
            for fname in ('compute_price', 'base', 'price_surcharge_percent_base'):
                if fname in vals and not vals[fname]:
                    del vals[fname]
            # Rules created from a variant only (imports, API) must also carry
            # the template, as the form view does through its onchange.
            if vals.get('product_id') and not vals.get('product_tmpl_id'):
                vals['product_tmpl_id'] = Product.browse(vals['product_id']).product_tmpl_id.id
            self._asp_resolve_import_packaging(vals)
        return super().create(vals_list)

    def write(self, vals):
        vals = self._asp_sanitize_vals(vals)
        # Required selections cannot be emptied (empty import cells): keep the current value.
        for fname in ('compute_price', 'base', 'price_surcharge_percent_base'):
            if fname in vals and not vals[fname]:
                vals = {k: v for k, v in vals.items() if k != fname}
        if len(self) == 1:
            vals = self._asp_resolve_import_packaging(
                vals, product_tmpl=self.product_tmpl_id, product=self.product_id)
        return super().write(vals)

    @api.model
    def get_import_templates(self):
        return [
            {
                'label': _("Pricelist rules - Multiple prices per product"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelist_rules_basic.xlsx',
            },
            {
                'label': _("Pricelist rules - Advanced price rules"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelist_rules_advanced.xlsx',
            },
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _asp_scope_uom(self):
        """UoM of the product the rule is scoped to (empty for category/global rules)."""
        self.ensure_one()
        if self.applied_on == '0_product_variant' and self.product_id:
            return self.product_id.uom_id
        if self.applied_on == '1_product' and self.product_tmpl_id:
            return self.product_tmpl_id.uom_id
        # Basic pricelist mode sets applied_on through an onchange; be lenient.
        return self.product_id.uom_id or self.product_tmpl_id.uom_id

    def _asp_unit_label(self):
        self.ensure_one()
        if self.packaging_id:
            return self.packaging_id.name
        if self.uom_id:
            return self.uom_id.name
        return ''

    def _asp_is_targeted(self):
        return bool(self) and self.asp_target in (TARGET_UOM, TARGET_PACKAGING)

    def _asp_pricing_targets(self, product):
        """Return the (uom, packaging) requested by the current pricing call."""
        ctx = self.env.context
        uom = self.env['uom.uom']
        packaging = self.env['product.packaging']
        if ctx.get(CTX_ENGINE):
            uom = uom.browse(ctx.get(CTX_UOM) or [])
            packaging = packaging.browse(ctx.get(CTX_PACKAGING) or [])
        return (uom or product.uom_id), packaging

    def _asp_rule_unit(self, product):
        """Pricing unit of a targeted rule.

        :return: tuple (uom, ratio) where ``ratio`` is the number of ``uom``
                 units contained in one rule unit (package qty or 1.0).
        """
        self.ensure_one()
        if self.packaging_id:
            return (self.packaging_id.product_uom_id or product.uom_id), self.packaging_id.qty
        if self.uom_id:
            return self.uom_id, 1.0
        return product.uom_id, 1.0

    def _asp_has_percent_fee(self):
        return bool(self) and self.compute_price == 'formula' and bool(self.price_surcharge_percent)

    def _asp_fee_basis_label(self):
        self.ensure_one()
        selection = dict(self._fields['price_surcharge_percent_base']._description_selection(self.env))
        return selection.get(self.price_surcharge_percent_base or 'base', '')

    def _asp_apply_formula(self, base_price, convert=None):
        """Odoo 17 formula (unchanged since 16.0), extended with the percentage extra fee.

        Same order as the standard engine: discount -> rounding -> extra fees
        -> min/max margins. ``base_price`` is expressed in the unit the result
        is wanted in; ``convert`` converts amounts the rule stores per product
        UoM (fixed extra fee and margins) into that unit.
        """
        self.ensure_one()
        convert = convert or (lambda amount: amount)
        price_limit = base_price
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
        return _(
            "%(base)s with a %(discount)s %% discount, %(surcharge)s extra fee and %(fee)s %% extra fee "
            "on the %(basis)s\nExample: %(amount)s → %(total)s",
            base=base_selection.get(self.base, ''),
            discount=self.price_discount,
            surcharge=tools.format_amount(self.env, self.price_surcharge, self.currency_id),
            fee=self.price_surcharge_percent,
            basis=self._asp_fee_basis_label().lower(),
            amount=tools.format_amount(self.env, 100, self.currency_id),
            total=tools.format_amount(self.env, example, self.currency_id),
        )

    @staticmethod
    def _asp_packaging_matches_product(packaging, product):
        if product._name == 'product.template':
            return packaging.product_id.product_tmpl_id == product
        return packaging.product_id == product

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------

    def _is_applicable_for(self, product, qty_in_product_uom):
        self.ensure_one()
        if not self._asp_is_targeted():
            return super()._is_applicable_for(product, qty_in_product_uom)

        product.ensure_one()
        target_uom, target_packaging = self._asp_pricing_targets(product)
        qty_precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        if self.packaging_id:
            packaging = self.packaging_id
            if packaging != target_packaging:
                return False
            if not self._asp_packaging_matches_product(packaging, product):
                return False
            if float_compare(packaging.qty, 0.0, precision_digits=qty_precision) <= 0:
                return False
            # packaging.qty is expressed in the product UoM
            rule_qty = qty_in_product_uom / packaging.qty
        else:
            if self.uom_id != target_uom or self.uom_id.category_id != product.uom_id.category_id:
                return False
            rule_qty = product.uom_id._compute_quantity(qty_in_product_uom, self.uom_id, round=False)

        if self.min_quantity and float_compare(rule_qty, self.min_quantity, precision_digits=qty_precision) < 0:
            return False
        # The min. quantity was checked in the rule unit: let the standard
        # implementation validate the scope (product / variant / category) only.
        return super()._is_applicable_for(product, max(qty_in_product_uom, self.min_quantity))

    def _compute_price(self, product, quantity, uom, date, currency=None):
        if len(self) != 1:
            return super()._compute_price(product, quantity, uom, date, currency=currency)
        if not self._asp_is_targeted():
            if not self._asp_has_percent_fee():
                return super()._compute_price(product, quantity, uom, date, currency=currency)
            # Generic formula rule with a percentage fee: same as the standard
            # formula (amounts stored per product UoM, base price in `uom`).
            product.ensure_one()
            uom.ensure_one()
            currency = currency or self.currency_id
            currency.ensure_one()
            product_uom = product.uom_id
            convert = (lambda p: product_uom._compute_price(p, uom)) if product_uom != uom else None
            base_price = self._compute_base_price(product, quantity, uom, date, currency)
            return self._asp_apply_formula(base_price, convert)

        product.ensure_one()
        uom.ensure_one()
        currency = currency or self.currency_id
        currency.ensure_one()

        unit_uom, ratio = self._asp_rule_unit(product)
        if unit_uom.category_id != uom.category_id or not ratio:
            # Should never happen for a matching rule; stay safe and standard.
            return super()._compute_price(product, quantity, uom, date, currency=currency)

        def to_requested_uom(price_per_rule_unit):
            return unit_uom._compute_price(price_per_rule_unit / ratio, uom)

        if self.compute_price == 'fixed':
            return to_requested_uom(self.fixed_price)

        # Base price for ONE rule unit (one package / one rule UoM).
        qty_in_unit_uom = uom._compute_quantity(quantity, unit_uom, round=False, raise_if_failure=False)
        base_price = self._compute_base_price(product, qty_in_unit_uom, unit_uom, date, currency) * ratio

        if self.compute_price == 'percentage':
            price = (base_price - (base_price * (self.percent_price / 100))) or 0.0
        elif self.compute_price == 'formula':
            # Amounts of a targeted rule are already per package / per rule UoM.
            price = self._asp_apply_formula(base_price)
        else:
            price = base_price
        return to_requested_uom(price)
