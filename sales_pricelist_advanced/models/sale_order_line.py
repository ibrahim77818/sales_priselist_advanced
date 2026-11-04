# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import float_compare, float_is_zero, float_round

from .product_pricelist_item import CTX_PACKAGING


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Technical trackers: remember in which UoM (and for which product) the
    # current quantity was typed, so a UoM change can convert it.
    asp_qty_uom_id = fields.Many2one(
        'uom.uom', string="Quantity Unit (technical)", copy=False, readonly=True)
    asp_qty_product_id = fields.Many2one(
        'product.product', string="Quantity Product (technical)", copy=False, readonly=True)

    asp_package_price = fields.Monetary(
        string="Price per Package",
        compute='_compute_asp_package_price',
        currency_field='currency_id',
        help="Unit price expressed per selected packaging (before discount).")

    def write(self, vals):
        # A product/UoM change that does not come from the form (API, import,
        # other modules) invalidates the trackers: fall back on stored values.
        if ('product_uom' in vals or 'product_id' in vals) and 'asp_qty_uom_id' not in vals:
            vals = dict(vals, asp_qty_uom_id=False, asp_qty_product_id=False)
        return super().write(vals)

    # ------------------------------------------------------------------
    # Pricing context
    # ------------------------------------------------------------------

    def _asp_pricing_context(self):
        self.ensure_one()
        return {CTX_PACKAGING: self.product_packaging_id.id or False}

    @api.depends('product_packaging_id')
    def _compute_pricelist_item_id(self):
        for line in self:
            super(SaleOrderLine, line.with_context(**line._asp_pricing_context()))._compute_pricelist_item_id()

    @api.depends('product_packaging_id')
    def _compute_price_unit(self):
        return super()._compute_price_unit()

    @api.depends('product_packaging_id')
    def _compute_discount(self):
        return super()._compute_discount()

    def _get_pricelist_price(self):
        self.ensure_one()
        return super(SaleOrderLine, self.with_context(**self._asp_pricing_context()))._get_pricelist_price()

    def _get_pricelist_price_before_discount(self):
        self.ensure_one()
        return super(SaleOrderLine, self.with_context(
            **self._asp_pricing_context()))._get_pricelist_price_before_discount()

    @api.depends('price_unit', 'product_uom', 'product_packaging_id', 'product_packaging_id.qty')
    def _compute_asp_package_price(self):
        for line in self:
            packaging = line.product_packaging_id
            if (
                not packaging
                or not line.product_uom
                or not packaging.product_uom_id
                or line.product_uom.category_id != packaging.product_uom_id.category_id
            ):
                line.asp_package_price = 0.0
                continue
            price_per_product_uom = line.product_uom._compute_price(line.price_unit, packaging.product_uom_id)
            line.asp_package_price = price_per_product_uom * packaging.qty

    def _asp_price_rounding_gap(self):
        """Amount lost on the subtotal because the unit price had to be rounded
        to the 'Product Price' precision (typical with package prices that are
        not divisible by the package quantity)."""
        self.ensure_one()
        if not self.product_id or not self.pricelist_item_id._asp_is_targeted():
            return 0.0
        line = self.with_company(self.company_id)
        exact_price = line.product_id._get_tax_included_unit_price_from_price(
            line._get_display_price(),
            line.currency_id or line.order_id.currency_id,
            product_taxes=line.product_id.taxes_id.filtered(lambda t: t.company_id == line.env.company),
            fiscal_position=line.order_id.fiscal_position_id,
        )
        currency = line.currency_id or line.order_id.currency_id
        gap = (exact_price - line.price_unit) * line.product_uom_qty
        return 0.0 if currency.is_zero(gap) else currency.round(gap)

    def _asp_rounding_warning(self):
        gap = self._asp_price_rounding_gap()
        if not gap:
            return {}
        return {
            'title': _("Unit price rounded"),
            'message': _(
                "The pricelist price of %(product)s cannot be expressed exactly per %(uom)s with the "
                "current decimal accuracy, so the line subtotal differs by %(gap)s. Increase the decimal "
                "accuracy of \"Product Price\" (Settings > Technical > Decimal Accuracy) to remove the gap.",
                product=self.product_id.display_name,
                uom=self.product_uom.name,
                gap=self.currency_id.round(gap) if self.currency_id else gap,
            ),
        }

    # ------------------------------------------------------------------
    # Quantity normalization (interactive)
    # ------------------------------------------------------------------

    # The conversion is done inside the quantity compute rather than in an
    # onchange: Odoo's own computes (packaging suggestion, packaging qty ->
    # quantity) read the quantity as soon as the UoM changes, and would
    # otherwise work on the *unconverted* number (e.g. "24 Dozens").

    def _asp_is_interactive(self):
        """Record being edited in a form (onchange), as opposed to a stored record."""
        return not self.id or isinstance(self.id, models.NewId)

    def _asp_qty_conversion(self):
        """Return (source_uom, exact_qty, rounded_qty) when the quantity must be
        converted after a UoM change, else None. Never called on stored records."""
        self.ensure_one()
        new_uom = self.product_uom
        prev_uom = self.asp_qty_uom_id or self._origin.product_uom
        prev_product = self.asp_qty_product_id or self._origin.product_id
        qty = self.product_uom_qty
        if (
            self.display_type
            or not self.company_id.asp_convert_qty_on_uom_change
            or not (self.product_id and new_uom and prev_uom)
            or prev_uom == new_uom
            or prev_product != self.product_id
            or prev_uom.category_id != new_uom.category_id
            or self.qty_delivered or self.qty_invoiced
            or float_is_zero(qty, precision_rounding=prev_uom.rounding)
        ):
            return None
        exact_qty = prev_uom._compute_quantity(qty, new_uom, round=False)
        new_qty = float_round(exact_qty, precision_rounding=new_uom.rounding, rounding_method='HALF-UP')
        if float_is_zero(new_qty, precision_rounding=new_uom.rounding):
            # Converting would wipe the quantity (e.g. 0.04 Unit -> Dozens): keep it.
            return None
        return prev_uom, exact_qty, new_qty

    @api.depends('product_uom')
    def _compute_product_uom_qty(self):
        converted = self.browse()
        rounding_log = self.env.cr.cache.setdefault('asp_qty_rounding', {})
        for line in self:
            if not line._asp_is_interactive():
                continue
            conversion = line._asp_qty_conversion()
            if conversion:
                prev_uom, exact_qty, new_qty = conversion
                if float_compare(exact_qty, new_qty, precision_digits=6) != 0:
                    rounding_log[line.id] = (line.product_uom_qty, prev_uom.name, new_qty, line.product_uom.name)
                line.product_uom_qty = new_qty
                converted |= line
        super(SaleOrderLine, self - converted)._compute_product_uom_qty()
        for line in self:
            if line._asp_is_interactive() and line.product_id:
                # The quantity is now expressed in the current UoM of the current product.
                line.asp_qty_uom_id = line.product_uom
                line.asp_qty_product_id = line.product_id

    @api.onchange('product_uom')
    def _asp_onchange_product_uom_normalize_qty(self):
        warning = {}
        # Reading the quantity forces the (lazy) conversion in _compute_product_uom_qty,
        # which also maintains the trackers; do not touch them here.
        self.product_uom_qty  # pylint: disable=pointless-statement
        logged = self.env.cr.cache.get('asp_qty_rounding', {}).pop(self.id, None)
        if logged:
            qty, old_uom, new_qty, new_uom = logged
            warning = {
                'title': _("Quantity rounded"),
                'message': _(
                    "%(qty)s %(old_uom)s converted to %(new_qty)s %(new_uom)s (rounded to the precision "
                    "of the unit of measure).",
                    qty=qty, old_uom=old_uom, new_qty=new_qty, new_uom=new_uom),
            }
        return self._asp_onchange_result(warning)

    @api.onchange('product_packaging_id')
    def _asp_onchange_packaging_round_qty(self):
        # NB: runs before the standard `_onchange_product_packaging_id` (alphabetical
        # order), so the standard "you should sell X" warning no longer triggers.
        warning = {}
        packaging = self.product_packaging_id
        if (
            packaging
            and self.company_id.asp_round_qty_to_packaging
            and self.product_uom
            and not self.qty_delivered and not self.qty_invoiced
        ):
            qty = self.product_uom_qty or 0.0
            if float_is_zero(qty, precision_rounding=self.product_uom.rounding):
                qty = 1.0
            new_qty = packaging._check_qty(qty, self.product_uom, "UP")
            if float_compare(new_qty, self.product_uom_qty, precision_rounding=self.product_uom.rounding) != 0:
                self.product_uom_qty = new_qty
                warning = {
                    'title': _("Quantity adjusted"),
                    'message': _(
                        "Quantity rounded up to %(qty)s %(uom)s to match whole packages of \"%(packaging)s\".",
                        qty=new_qty, uom=self.product_uom.name, packaging=packaging.name),
                }
        return self._asp_onchange_result(warning)

    def _asp_onchange_result(self, warning):
        rounding_warning = self._asp_rounding_warning() if self.product_id else {}
        warnings = [w for w in (warning, rounding_warning) if w]
        if not warnings:
            return None
        return {
            'warning': {
                'title': warnings[0]['title'],
                'message': "\n\n".join(w['message'] for w in warnings),
                'type': 'notification',
            }
        }
