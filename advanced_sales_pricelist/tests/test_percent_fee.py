# -*- coding: utf-8 -*-
"""Percentage extra fee on formula rules."""
from odoo import fields
from odoo.tests import Form, tagged

from .common import AspCommon


@tagged('post_install', '-at_install', 'asp')
class TestPercentFee(AspCommon):
    """Water Bottle: list 10.00 / Unit, cost 6.00, Carton of 24."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref('product.group_sale_pricelist')

    def _fee_rule(self, pricelist=None, **vals):
        return self._product_item(pricelist, compute_price='formula', **vals)

    # ------------------------------------------------------------ formula
    def test_fee_on_base_price(self):
        self._fee_rule(price_discount=10, price_surcharge_percent=5)
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 9.5)  # 9 + 5% of 10

    def test_fee_on_discounted_price(self):
        self._fee_rule(price_discount=10, price_surcharge_percent=5, price_surcharge_percent_base='discounted')
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 9.45)  # 9 + 5% of 9

    def test_fee_after_rounding(self):
        # 10 -7% = 9.3 -> rounded to 1.0 = 9 -> +10% of 9 = 9.9
        self._fee_rule(price_discount=7, price_round=1.0, price_surcharge_percent=10,
                       price_surcharge_percent_base='discounted')
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 9.9)

    def test_fixed_and_percent_fees_combined(self):
        self._fee_rule(base='standard_price', price_surcharge=0.5, price_surcharge_percent=30)
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 8.3)  # 6 + 0.5 + 1.8

    def test_negative_fee_is_a_rebate(self):
        self._fee_rule(price_surcharge_percent=-15)
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 8.5)

    def test_margins_apply_after_fee(self):
        pl_max = self._create_pricelist('fee max')
        self._fee_rule(pl_max, price_surcharge_percent=50, price_max_margin=2.0)
        pl_min = self._create_pricelist('fee min')
        self._fee_rule(pl_min, price_discount=50, price_surcharge_percent=10, price_min_margin=-1.0)
        self.assertAlmostEqual(self._price(pl_max, self.product, 1), 12.0)   # 15 capped to 10 + 2
        self.assertAlmostEqual(self._price(pl_min, self.product, 1), 9.0)    # 6 raised to 10 - 1

    def test_fee_based_on_other_pricelist(self):
        base_pl = self._create_pricelist('fee base')
        self._product_item(base_pl, fixed_price=8.0)
        self._fee_rule(base='pricelist', base_pricelist_id=base_pl.id, price_surcharge_percent=25)
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 10.0)

    def test_fee_scales_with_line_uom(self):
        self._fee_rule(price_discount=10, price_surcharge=1.0, price_surcharge_percent=5)
        # per Dozen: 120 -10% = 108 + 12 (fixed fee per unit x 12) + 6 (5% of 120)
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1, uom=self.uom_dozen), 126.0)

    def test_zero_fee_keeps_standard_engine(self):
        rule = self._fee_rule(price_discount=10, price_surcharge=0.5)
        self.assertFalse(rule._asp_has_percent_fee())
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 9.5)

    def test_fee_ignored_for_non_formula_rules(self):
        self._product_item(compute_price='percentage', percent_price=10, price_surcharge_percent=50)
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 9.0)

    # ------------------------------------------------ targeted rules
    def test_fee_on_packaging_rule(self):
        # carton base 240 -10% = 216 + 2% of 240 (4.8) = 220.8 per carton
        self._fee_rule(packaging_id=self.carton.id, price_discount=10, price_surcharge_percent=2)
        line = self._line(self._order(), qty=24, packaging=self.carton)
        self.assertAlmostEqual(line.price_unit * 24, 220.8, places=4)
        self.assertAlmostEqual(line.price_subtotal, 220.8, places=2)

    def test_fee_on_uom_rule(self):
        # 120 per dozen, rounded to 5 after -3% (116.4 -> 115), +4% of 115 = 119.6
        self._fee_rule(uom_id=self.uom_dozen.id, price_discount=3, price_round=5.0, price_surcharge_percent=4,
                       price_surcharge_percent_base='discounted')
        line = self._line(self._order(), qty=1, uom=self.uom_dozen, packaging=False)
        self.assertAlmostEqual(line.price_unit, 119.6, places=6)

    # ------------------------------------------------ sales / currency
    def test_fee_shown_as_negative_discount_is_hidden(self):
        """With 'show discount' policy, a net mark-up is not displayed as a discount."""
        pricelist = self._create_pricelist('fee shown', policy='without_discount')
        self._fee_rule(pricelist, price_surcharge_percent=10)
        line = self._line(self._order(pricelist), qty=1, packaging=False)
        self.assertAlmostEqual(line.price_unit, 11.0)
        self.assertAlmostEqual(line.discount, 0.0)

    def test_fee_with_shown_discount(self):
        pricelist = self._create_pricelist('fee discount', policy='without_discount')
        self._fee_rule(pricelist, price_discount=20, price_surcharge_percent=5)
        line = self._line(self._order(pricelist), qty=1, packaging=False)
        self.assertAlmostEqual(line.price_unit, 10.0)
        self.assertAlmostEqual(line.discount, 15.0, places=4)  # 8.5 vs 10
        self.assertAlmostEqual(line.price_subtotal, 8.5, places=2)

    def test_fee_in_foreign_currency(self):
        usd, eur = self.env.ref('base.USD'), self.env.ref('base.EUR')
        foreign = eur if self.currency == usd else usd
        foreign.active = True
        self.env['res.currency.rate'].search([('currency_id', 'in', (foreign | self.currency).ids)]).unlink()
        self.env['res.currency.rate'].create({
            'name': fields.Date.from_string('2000-01-01'), 'rate': 2.0,
            'currency_id': foreign.id, 'company_id': self.company.id})
        pricelist = self._create_pricelist('fee foreign', currency=foreign)
        self._fee_rule(pricelist, price_surcharge=1.0, price_surcharge_percent=10)
        # base 20 (foreign) + 1 fixed (pricelist currency) + 10 % of 20
        self.assertAlmostEqual(self._price(pricelist, self.product, 1), 23.0)

    # ------------------------------------------------------- UI
    def test_rule_form_and_labels(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.applied_on = '1_product'
            item.product_tmpl_id = self.tmpl
            item.compute_price = 'formula'
            item.price_discount = 10
            item.price_surcharge_percent = 5
            item.price_surcharge_percent_base = 'discounted'
        form.save()
        rule = self.pricelist.item_ids
        self.assertIn('5.0', rule.price)
        self.assertIn('94.50', rule.rule_tip.replace(',', '.'))  # example on 100.00
        line = self._line(self._order(), qty=1, packaging=False)
        self.assertAlmostEqual(line.price_unit, 9.45)

    def test_switching_away_from_formula_resets_fee(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.applied_on = '1_product'
            item.product_tmpl_id = self.tmpl
            item.compute_price = 'formula'
            item.price_surcharge_percent = 5
            item.price_surcharge_percent_base = 'discounted'
            item.compute_price = 'fixed'
            self.assertEqual(item.price_surcharge_percent, 0.0)
            self.assertEqual(item.price_surcharge_percent_base, 'base')
            item.fixed_price = 7.0
        form.save()
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 7.0)
