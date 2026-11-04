# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import float_compare, float_is_zero, float_round

from .product_pricelist_item import uom_root


def _fmt_qty(qty):
    """Quantity for messages: 2.0 -> "2", 1.25 -> "1.25"."""
    return ('%.4f' % qty).rstrip('0').rstrip('.')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Technical trackers: remember in which unit (and for which product) the
    # current quantity was typed, so a unit / packaging change can convert it.
    asp_qty_uom_id = fields.Many2one(
        'uom.uom', string="Quantity Unit (technical)", copy=False, readonly=True)
    asp_qty_product_id = fields.Many2one(
        'product.product', string="Quantity Product (technical)", copy=False, readonly=True)

    def write(self, vals):
        # A product/unit change that does not come from the form (API, import,
        # other modules) invalidates the trackers: fall back on stored values.
        if ('product_uom_id' in vals or 'product_id' in vals) and 'asp_qty_uom_id' not in vals:
            vals = dict(vals, asp_qty_uom_id=False, asp_qty_product_id=False)
        return super().write(vals)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _asp_is_interactive(self):
        """Record being edited in a form (onchange), as opposed to a stored record."""
        # Odoo 19 moved NewId out of odoo.models: a stored record has an integer id.
        return not isinstance(self.id, int)

    def _asp_is_packaging_uom(self, uom=None):
        """Odoo 19: a packaging is a unit listed in the product's Packagings (uom_ids)."""
        self.ensure_one()
        uom = uom or self.product_uom_id
        return bool(uom) and uom in self.product_id.uom_ids

    def _asp_whole_packages(self, qty, uom):
        """Quantity rounded up to whole packages when ``uom`` is a packaging of the
        product and the company setting is enabled, else ``qty`` unchanged."""
        self.ensure_one()
        if (
            self.company_id.asp_round_qty_to_packaging
            and self._asp_is_packaging_uom(uom)
            and not self.qty_delivered and not self.qty_invoiced
        ):
            return float_round(qty, precision_rounding=1.0, rounding_method='UP')
        return qty

    # ------------------------------------------------------------------
    # Quantity normalization (interactive)
    # ------------------------------------------------------------------

    # The conversion is done inside the quantity compute rather than in an
    # onchange so that every compute depending on the quantity (price, rule,
    # discount) works on the converted number.

    def _asp_qty_conversion(self):
        """Return (source_uom, exact_qty, new_qty) when the quantity must be
        converted after a unit change, else None. Never called on stored records."""
        self.ensure_one()
        new_uom = self.product_uom_id
        prev_uom = self.asp_qty_uom_id or self._origin.product_uom_id
        prev_product = self.asp_qty_product_id or self._origin.product_id
        qty = self.product_uom_qty
        if (
            self.display_type
            or not self.company_id.asp_convert_qty_on_uom_change
            or not (self.product_id and new_uom and prev_uom)
            or prev_uom == new_uom
            or prev_product != self.product_id
            or uom_root(prev_uom) != uom_root(new_uom)
            or self.qty_delivered or self.qty_invoiced
            or float_is_zero(qty, precision_rounding=prev_uom.rounding)
        ):
            return None
        exact_qty = prev_uom._compute_quantity(qty, new_uom, round=False)
        new_qty = self._asp_whole_packages(exact_qty, new_uom)
        new_qty = float_round(new_qty, precision_rounding=new_uom.rounding, rounding_method='HALF-UP')
        if float_is_zero(new_qty, precision_rounding=new_uom.rounding):
            # Converting would wipe the quantity (e.g. 0.04 Unit -> Dozens): keep it.
            return None
        return prev_uom, exact_qty, new_qty

    @api.depends('product_uom_id')
    def _compute_product_uom_qty(self):
        converted = self.browse()
        log = self.env.cr.cache.setdefault('asp_qty_conversion', {})
        for line in self:
            if not line._asp_is_interactive():
                continue
            conversion = line._asp_qty_conversion()
            if conversion:
                prev_uom, exact_qty, new_qty = conversion
                if float_compare(exact_qty, new_qty, precision_digits=6) != 0:
                    log[line.id] = (line.product_uom_qty, prev_uom.name, exact_qty, new_qty,
                                    line.product_uom_id.name)
                line.product_uom_qty = new_qty
                converted |= line
        super(SaleOrderLine, self - converted)._compute_product_uom_qty()
        for line in self:
            if line._asp_is_interactive() and line.product_id:
                # The quantity is now expressed in the current unit of the current product.
                line.asp_qty_uom_id = line.product_uom_id
                line.asp_qty_product_id = line.product_id

    @api.onchange('product_uom_id')
    def _asp_onchange_product_uom_normalize_qty(self):
        # Reading the quantity forces the (lazy) conversion in _compute_product_uom_qty,
        # which also maintains the trackers; do not touch them here.
        self.product_uom_qty  # pylint: disable=pointless-statement
        logged = self.env.cr.cache.get('asp_qty_conversion', {}).pop(self.id, None)
        if not logged:
            return None
        qty, old_uom, exact_qty, new_qty, new_uom = logged
        if float_compare(new_qty, exact_qty, precision_digits=6) > 0 and self._asp_is_packaging_uom():
            title = _("Quantity adjusted")
            message = _(
                "%(qty)s %(old_uom)s = %(exact)s %(new_uom)s: rounded up to %(new_qty)s %(new_uom)s "
                "to sell whole packages.",
                qty=_fmt_qty(qty), old_uom=old_uom, exact=_fmt_qty(exact_qty), new_qty=_fmt_qty(new_qty),
                new_uom=new_uom)
        else:
            title = _("Quantity rounded")
            message = _(
                "%(qty)s %(old_uom)s converted to %(new_qty)s %(new_uom)s (rounded to the precision "
                "of the unit of measure).",
                qty=_fmt_qty(qty), old_uom=old_uom, new_qty=_fmt_qty(new_qty), new_uom=new_uom)
        return {'warning': {'title': title, 'message': message, 'type': 'notification'}}

    @api.onchange('product_uom_qty')
    def _asp_onchange_qty_whole_packages(self):
        """A fractional quantity typed in a packaging unit is rounded up to whole packages."""
        if not (self.product_id and self.product_uom_id) or self.display_type:
            return None
        qty = self.product_uom_qty or 0.0
        new_qty = self._asp_whole_packages(qty, self.product_uom_id)
        if float_compare(new_qty, qty, precision_rounding=self.product_uom_id.rounding) <= 0:
            return None
        self.product_uom_qty = new_qty
        return {
            'warning': {
                'title': _("Quantity adjusted"),
                'message': _(
                    "Quantity rounded up to %(qty)s %(uom)s to sell whole packages.",
                    qty=_fmt_qty(new_qty), uom=self.product_uom_id.name),
                'type': 'notification',
            }
        }
