# -*- coding: utf-8 -*-
from odoo import _, api, models


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
                'label': _("Pricelists with rules - All rule types (discounts, surcharges)"),
                'template': '/sales_pricelist_advanced/static/xls/asp_pricelists_advanced.xlsx',
            },
        ]

    # Odoo 20 passes the requested unit to rule matching and pricing (including
    # chained pricelists): no engine override is needed for unit / packaging rules.
