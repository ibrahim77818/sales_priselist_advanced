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
        cls.env.user.groups_id |= cls.env.ref('product.group_sale_pricelist')
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
        self._product_item(self.foreign_pl, packaging_id=self.carton.id, fixed_price=400.0)
        order = self._order(self.foreign_pl)
        line = self._line(order, qty=24, packaging=self.carton)
        self.assertEqual(order.currency_id, self.foreign)
        self.assertAlmostEqual(line.price_unit, 400.0 / 24, places=6)
        self.assertAlmostEqual(line.price_subtotal, 400.0, places=2)

    def test_formula_package_price_converted(self):
        # list 10 -> 20 foreign per unit -> 480 per carton -> -10 % = 432
        self._product_item(self.foreign_pl, packaging_id=self.carton.id,
                           compute_price='formula', price_discount=10)
        line = self._line(self._order(self.foreign_pl), qty=24, packaging=self.carton)
        self.assertAlmostEqual(line.price_unit, 18.0, places=6)
        self.assertAlmostEqual(line.price_subtotal, 432.0, places=2)

    def test_uom_surcharge_in_pricelist_currency(self):
        # 120 per dozen -> 240 foreign, +5 foreign fee per dozen = 245
        self._product_item(self.foreign_pl, uom_id=self.uom_dozen.id,
                           compute_price='formula', price_surcharge=5.0)
        line = self._line(self._order(self.foreign_pl), qty=2, uom=self.uom_dozen, packaging=False)
        self.assertAlmostEqual(line.price_unit, 245.0, places=6)
        self.assertAlmostEqual(line.order_id.amount_untaxed, 490.0, places=2)

    def test_no_rule_falls_back_on_converted_list_price(self):
        line = self._line(self._order(self.foreign_pl), qty=24, packaging=self.carton)
        self.assertFalse(line.pricelist_item_id)
        self.assertAlmostEqual(line.price_unit, 20.0, places=6)

    def test_chained_pricelist_cross_currency(self):
        base_pl = self._create_pricelist('Company currency base')
        self._product_item(base_pl, packaging_id=self.carton.id, fixed_price=216.0)
        self._item(self.foreign_pl, applied_on='3_global', compute_price='formula',
                   base='pricelist', base_pricelist_id=base_pl.id)
        order = self._order(self.foreign_pl)
        carton = self._line(order, qty=24, packaging=self.carton)
        units = self._line(order, qty=5, packaging=False)
        self.assertAlmostEqual(carton.price_unit, 18.0, places=6)   # 9 * 2
        self.assertAlmostEqual(units.price_unit, 20.0, places=6)    # 10 * 2

    def test_reverse_chain_foreign_base(self):
        """Company-currency pricelist based on a foreign-currency pricelist."""
        self._product_item(self.foreign_pl, packaging_id=self.carton.id, fixed_price=480.0)  # 20/u foreign
        company_pl = self._create_pricelist('Company currency chained')
        self._item(company_pl, applied_on='3_global', compute_price='formula',
                   base='pricelist', base_pricelist_id=self.foreign_pl.id, price_discount=50)
        line = self._line(self._order(company_pl), qty=24, packaging=self.carton)
        self.assertAlmostEqual(line.price_unit, 5.0, places=6)  # 20 foreign -> 10 -> -50 %

    def test_without_discount_cross_currency(self):
        pricelist = self._create_pricelist('Foreign show discount', currency=self.foreign,
                                           policy='without_discount')
        self._product_item(pricelist, packaging_id=self.carton.id, fixed_price=360.0)
        line = self._line(self._order(pricelist), qty=24, packaging=self.carton)
        self.assertAlmostEqual(line.price_unit, 20.0, places=6)
        self.assertAlmostEqual(line.discount, 25.0, places=4)
        self.assertAlmostEqual(line.price_subtotal, 360.0, places=2)
