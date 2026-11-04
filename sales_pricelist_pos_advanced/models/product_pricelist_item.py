# -*- coding: utf-8 -*-
from odoo import api, models

GENERIC = '2_any'


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    # Odoo 19: pricelist rules reach the POS through pos.load.mixin.

    @api.model
    def _load_pos_data_domain(self, data, config):
        # POS order lines are always in the product unit (a packaging barcode
        # adds its quantity in that unit): rules for another unit or packaging
        # must never reach the POS.
        return super()._load_pos_data_domain(data, config) + [('asp_target', '=', GENERIC)]

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        extra = ['asp_target', 'price_surcharge_percent', 'price_surcharge_percent_base']
        return fields + [fname for fname in extra if fname not in fields]
