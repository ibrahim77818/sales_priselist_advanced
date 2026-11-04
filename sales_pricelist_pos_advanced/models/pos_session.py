# -*- coding: utf-8 -*-
from odoo import models

GENERIC = '2_any'


class PosSession(models.Model):
    _inherit = 'pos.session'

    def get_pos_ui_product_pricelist_item_by_product(self, product_tmpl_ids, product_ids, config_id):
        # Rules of products loaded later (search, barcode scan, cached products).
        result = super().get_pos_ui_product_pricelist_item_by_product(product_tmpl_ids, product_ids, config_id)
        items = result.get('product.pricelist.item', [])
        result['product.pricelist.item'] = [item for item in items if item.get('asp_target', GENERIC) == GENERIC]
        return result
