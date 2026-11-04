# -*- coding: utf-8 -*-
from odoo import _, api, models

from .product_pricelist_item import CTX_ENGINE, CTX_PACKAGING, CTX_UOM


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    # Fields that must never be emptied: an empty import cell means "default"
    # (company currency / discount included). A pricelist without discount
    # policy would make sales order lines show the public price without the
    # discount, i.e. a wrong price.
    _ASP_KEEP_DEFAULT_FIELDS = ('currency_id', 'discount_policy')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            for fname in self._ASP_KEEP_DEFAULT_FIELDS:
                if fname in vals and not vals[fname]:
                    del vals[fname]
        return super().create(vals_list)

    def write(self, vals):
        if any(fname in vals and not vals[fname] for fname in self._ASP_KEEP_DEFAULT_FIELDS):
            vals = {k: v for k, v in vals.items() if not (k in self._ASP_KEEP_DEFAULT_FIELDS and not v)}
        return super().write(vals)

    def get_import_templates(self):
        return super().get_import_templates() + [
            {
                'label': _("Pricelists with rules - Multiple prices per product"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelists_basic.xlsx',
            },
            {
                'label': _("Pricelists with rules - Advanced price rules"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelists_advanced.xlsx',
            },
        ]

    def _asp_resolve_packaging(self, packaging):
        """Normalize a packaging given as record, id or None (falls back on context)."""
        Packaging = self.env['product.packaging']
        if packaging is None:
            return Packaging.browse(self.env.context.get(CTX_PACKAGING) or [])
        if isinstance(packaging, int):
            return Packaging.browse(packaging)
        return packaging or Packaging

    def _compute_price_rule(self, products, qty, uom=None, date=False, **kwargs):
        """Make the requested UoM and packaging available to rule matching.

        Callers may pass ``packaging=<product.packaging>`` explicitly; otherwise
        the packaging is read from the context (``asp_packaging_id``), which lets
        it propagate to chained pricelists (rules based on another pricelist).
        """
        packaging = self._asp_resolve_packaging(kwargs.get('packaging'))
        pricing_ctx = {
            CTX_ENGINE: True,
            CTX_UOM: uom.id if uom else False,
            CTX_PACKAGING: packaging.id if packaging else False,
        }
        return super(ProductPricelist, self.with_context(**pricing_ctx))._compute_price_rule(
            products, qty, uom=uom, date=date, **kwargs)

    def _get_applicable_rules_domain(self, products, date, **kwargs):
        domain = super()._get_applicable_rules_domain(products, date, **kwargs)
        ctx = self.env.context
        if not ctx.get(CTX_ENGINE):
            # Unknown caller: packaging rules can never match without a packaging.
            return domain + [('packaging_id', '=', False)]

        uom_ids = [ctx[CTX_UOM]] if ctx.get(CTX_UOM) else products.uom_id.ids
        domain += ['|', ('uom_id', '=', False), ('uom_id', 'in', uom_ids)]
        if ctx.get(CTX_PACKAGING):
            domain += ['|', ('packaging_id', '=', False), ('packaging_id', '=', ctx[CTX_PACKAGING])]
        else:
            domain += [('packaging_id', '=', False)]
        return domain
