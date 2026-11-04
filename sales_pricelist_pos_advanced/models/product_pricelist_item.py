# -*- coding: utf-8 -*-
from odoo import api, models

GENERIC = '2_any'


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    # Odoo 18: pricelist rules reach the POS through pos.load.mixin.

    @api.model
    def _load_pos_data_domain(self, data):
        # The POS client only sells in the product UoM and has no packaging
        # context: UoM / packaging targeted rules must never reach it.
        return super()._load_pos_data_domain(data) + [('asp_target', '=', GENERIC)]

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        extra = ['asp_target', 'price_surcharge_percent', 'price_surcharge_percent_base']
        return fields + [fname for fname in extra if fname not in fields]
