# -*- coding: utf-8 -*-
"""Multi-currency: pricelist currency differs from the product (company) currency."""
from odoo import fields
from odoo.tests import tagged

from .common import AspCommon


@tagged('post_install', '-at_install', 'asp')
class TestCurrencyNormalization(AspCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        usd, eur = cls.env.ref('base.USD'), cls.env.ref('base.EUR')
        cls.foreign = eur if cls.currency == usd else usd
        cls.foreign.active = True
        # 1 company currency = 2 foreign currency
        cls.env['res.currency.rate'].search([('currency_id', 'in', (cls.foreign | cls.currency).ids)]).unlink()
        cls.env['res.currency.rate'].create({
            'name': fields.Date.from_string('2000-01-01'),
            'rate': 2.0,
            'currency_id': cls.foreign.id,
            'company_id': cls.company.id,
        })
        cls.foreign_pl = cls._create_pricelist('Foreign', currency=cls.foreign)

    def test_fixed_package_price_is_not_converted(self):
        self._product_item(self.foreign_pl, uom_id=self.carton.id, fixed_price=400.0)
        order = self._order(self.foreign_pl)
        line = self._line(order, qty=1, uom=self.carton)
        self.assertEqual(order.currency_id, self.foreign)
        self.assertAlmostEqual(line.price_unit, 400.0, places=6)

    def test_formula_package_price_converted(self):
        # list 10 -> 20 foreign per unit -> 480 per carton -> -10 % = 432
        self._product_item(self.foreign_pl, uom_id=self.carton.id, compute_price='formula', price_discount=10)
        line = self._line(self._order(self.foreign_pl), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 432.0, places=6)

    def test_uom_surcharge_in_pricelist_currency(self):
        # 120 per dozen -> 240 foreign, +5 foreign fee per dozen = 245
        self._product_item(self.foreign_pl, uom_id=self.uom_dozen.id, compute_price='formula', price_surcharge=5.0)
        line = self._line(self._order(self.foreign_pl), qty=2, uom=self.uom_dozen)
        self.assertAlmostEqual(line.price_unit, 245.0, places=6)
        self.assertAlmostEqual(line.order_id.amount_untaxed, 490.0, places=2)

    def test_no_rule_falls_back_on_converted_list_price(self):
        line = self._line(self._order(self.foreign_pl), qty=1, uom=self.carton)
        self.assertFalse(line.pricelist_item_id)
        self.assertAlmostEqual(line.price_unit, 480.0, places=6)

    def test_chained_pricelist_cross_currency(self):
        base_pl = self._create_pricelist('Company currency base')
        self._product_item(base_pl, uom_id=self.carton.id, fixed_price=216.0)
        self._item(self.foreign_pl, applied_on='3_global', compute_price='formula',
                   base='pricelist', base_pricelist_id=base_pl.id)
        order = self._order(self.foreign_pl)
        self.assertAlmostEqual(self._line(order, qty=1, uom=self.carton).price_unit, 432.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=5).price_unit, 20.0, places=6)

    def test_reverse_chain_foreign_base(self):
        """Company-currency pricelist based on a foreign-currency pricelist."""
        self._product_item(self.foreign_pl, uom_id=self.carton.id, fixed_price=480.0)
        company_pl = self._create_pricelist('Company currency chained')
        self._item(company_pl, applied_on='3_global', compute_price='formula',
                   base='pricelist', base_pricelist_id=self.foreign_pl.id, price_discount=50)
        line = self._line(self._order(company_pl), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 120.0, places=6)  # 480 foreign -> 240 -> -50 %

    def test_discount_shown_cross_currency(self):
        self._enable_discount_display()
        pricelist = self._create_pricelist('Foreign show discount', currency=self.foreign)
        self._product_item(pricelist, uom_id=self.carton.id, compute_price='percentage', percent_price=25)
        line = self._line(self._order(pricelist), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 480.0, places=6)
        self.assertAlmostEqual(line.discount, 25.0, places=4)
        self.assertAlmostEqual(line.price_subtotal, 360.0, places=2)
