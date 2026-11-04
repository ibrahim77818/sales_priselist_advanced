# -*- coding: utf-8 -*-
from odoo import _, api, models

from .product_pricelist_item import CTX_ENGINE, CTX_UOM


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    # Fields that must never be emptied: an empty import cell means "default"
    # (company currency). Odoo 18+ has no pricelist discount policy.
    _ASP_KEEP_DEFAULT_FIELDS = ('currency_id',)

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
                'label': _("Pricelists with rules - Fixed prices (product, unit, packaging)"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelists_basic.xlsx',
            },
            {
                'label': _("Pricelists with rules - All rule types (discounts, formulas)"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelists_advanced.xlsx',
            },
        ]

    def _compute_price_rule(
            self, products, quantity, *, currency=None, uom=None, date=False, compute_price=True,
            **kwargs
    ):
        """Make the requested unit (or packaging, which is a unit in Odoo 19)
        available to rule matching, including in chained pricelists."""
        pricing_ctx = {
            CTX_ENGINE: True,
            CTX_UOM: uom.id if uom else False,
        }
        return super(ProductPricelist, self.with_context(**pricing_ctx))._compute_price_rule(
            products, quantity, currency=currency, uom=uom, date=date, compute_price=compute_price,
            **kwargs)

    def _get_applicable_rules_domain(self, products, date, **kwargs):
        domain = super()._get_applicable_rules_domain(products, date, **kwargs)
        ctx = self.env.context
        if ctx.get(CTX_ENGINE) and ctx.get(CTX_UOM):
            uom_ids = [ctx[CTX_UOM]]
        else:
            uom_ids = products.uom_id.ids
        return domain + ['|', ('uom_id', '=', False), ('uom_id', 'in', uom_ids)]
