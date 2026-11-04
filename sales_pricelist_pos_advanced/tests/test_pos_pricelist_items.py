# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.sales_pricelist_advanced.tests.common import AspCommon


@tagged('post_install', '-at_install', 'asp')
class TestPosPricelistItems(AspCommon):

    def _pos_data(self):
        """Minimal loader payload, as built by pos.session.load_data (Odoo 18)."""
        return {
            'product.product': {'data': [{'id': self.product.id, 'product_tmpl_id': self.tmpl.id}]},
            'product.pricelist': {'data': [{'id': self.pricelist.id}]},
        }

    def test_targeted_rules_not_sent_to_pos(self):
        generic = self._product_item(fixed_price=9.5)
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        Item = self.env['product.pricelist.item']
        items = Item.search(Item._load_pos_data_domain(self._pos_data()))
        self.assertEqual(items, generic)
        fields = Item._load_pos_data_fields(False)
        for fname in ('asp_target', 'price_surcharge_percent', 'price_surcharge_percent_base'):
            self.assertIn(fname, fields)

    def test_targeted_rules_not_sent_on_demand(self):
        generic = self._product_item(fixed_price=9.5)
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        session = self.env['pos.session']
        # the pricelist must be available in the session config
        config = self.env['pos.config'].create({
            'name': 'ASP config', 'use_pricelist': True, 'pricelist_id': self.pricelist.id,
            'available_pricelist_ids': [(6, 0, self.pricelist.ids)]})
        session = session.new({'config_id': config.id, 'company_id': self.env.company.id})
        result = session.get_pos_ui_product_pricelist_item_by_product(
            [self.tmpl.id], [self.product.id], config.id)
        self.assertEqual([item['id'] for item in result['product.pricelist.item']], [generic.id])

    def test_backend_pricing_unchanged(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        line = self._line(self._order(), qty=24, packaging=self.carton)
        self.assertAlmostEqual(line.price_unit, 9.0, places=6)
