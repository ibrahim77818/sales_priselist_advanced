# -*- coding: utf-8 -*-
"""Runs the real POS client in a headless browser and checks that the browser
price engine applies the percentage extra fee exactly like the backend."""
from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged('post_install', '-at_install', 'asp')
class TestAspPosUi(TestPointOfSaleHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.fee_product = env['product.product'].create({
            'name': 'ASP POS Fee Product',
            'available_in_pos': True,
            'list_price': 100.0,
            'standard_price': 50.0,
            'taxes_id': [Command.clear()],
        })
        tmpl = cls.fee_product.product_tmpl_id
        Pricelist = env['product.pricelist']

        def pricelist(name, *rules):
            return Pricelist.create({
                'name': name,
                'item_ids': [Command.create(dict(
                    {'applied_on': '1_product', 'product_tmpl_id': tmpl.id, 'compute_price': 'formula'},
                    **rule)) for rule in rules],
            })

        on_base = pricelist('ASP POS Fee on base', {'price_discount': 10, 'price_surcharge_percent': 5})
        cls.pos_pricelists = (
            on_base
            | pricelist('ASP POS Fee on discounted', {
                'price_discount': 10, 'price_surcharge_percent': 5, 'price_surcharge_percent_base': 'discounted'})
            | pricelist('ASP POS Fee rounded', {
                'price_discount': 7, 'price_round': 5.0, 'price_surcharge_percent': 10,
                'price_surcharge_percent_base': 'discounted'})
            | pricelist('ASP POS Fee on cost', {
                'base': 'standard_price', 'price_surcharge_percent': 30, 'price_surcharge': 2.0})
            | pricelist('ASP POS Fee markup on cost', {
                'base': 'standard_price', 'price_markup': 30, 'price_surcharge_percent': 10})
            | pricelist('ASP POS Fee capped', {'price_surcharge_percent': 50, 'price_max_margin': 20.0})
            | pricelist('ASP POS Fee chained', {
                'base': 'pricelist', 'base_pricelist_id': on_base.id, 'price_surcharge_percent': 5})
            | pricelist('ASP POS Fee min qty', {'price_surcharge_percent': 10, 'min_quantity': 10})
            | pricelist('ASP POS No fee', {'price_discount': 10})
        )
        # Odoo 19: a packaging is a unit listed in the product's Packagings
        box = env['uom.uom'].create({'name': 'ASP Box of 5', 'relative_factor': 5,
                                     'relative_uom_id': env.ref('uom.product_uom_unit').id})
        cls.fee_product.uom_ids = box
        cls.pos_pricelists |= pricelist('ASP POS Packaging only', {
            'compute_price': 'fixed', 'fixed_price': 450.0, 'uom_id': box.id})
        cls.main_pos_config.write({
            'use_pricelist': True,
            'available_pricelist_ids': [Command.link(pl.id) for pl in cls.pos_pricelists],
        })

    def test_backend_expected_prices(self):
        """The values hard-coded in the tour are the backend engine results."""
        expected = {
            ('ASP POS Fee on base', 1): 95.0,
            ('ASP POS Fee on discounted', 1): 94.5,
            ('ASP POS Fee rounded', 1): 104.5,
            ('ASP POS Fee on cost', 1): 67.0,
            ('ASP POS Fee markup on cost', 1): 70.0,
            ('ASP POS Fee capped', 1): 120.0,
            ('ASP POS Fee chained', 1): 99.75,
            ('ASP POS Fee min qty', 1): 100.0,
            ('ASP POS Fee min qty', 10): 110.0,
            ('ASP POS No fee', 1): 90.0,
            ('ASP POS Packaging only', 5): 100.0,
        }
        by_name = {pl.name: pl for pl in self.pos_pricelists}
        for (name, qty), price in expected.items():
            self.assertAlmostEqual(by_name[name]._get_product_price(self.fee_product, qty), price, places=6,
                                   msg="%s x%s" % (name, qty))

    def test_pos_client_applies_percentage_fee(self):
        self.main_pos_config.with_user(self.pos_user).open_ui()
        self.start_pos_tour('asp_pos_percent_fee_tour')
