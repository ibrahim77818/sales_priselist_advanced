# -*- coding: utf-8 -*-
"""Pricelist mode 1: "Multiple prices per product" (fixed prices per product)."""
from odoo.tests import tagged

from .common import AspCommon


@tagged('post_install', '-at_install', 'asp')
class TestBasicPricing(AspCommon):

    # ---------------------------------------------------------- packaging
    def test_packaging_fixed_price_on_order_line(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        order = self._order()
        line = self._line(order, qty=24, packaging=self.carton)
        self.assertEqual(line.pricelist_item_id.packaging_id, self.carton)
        self.assertAlmostEqual(line.price_unit, 9.0, places=6)
        self.assertAlmostEqual(line.price_subtotal, 216.0, places=2)
        self.assertAlmostEqual(line.asp_package_price, 216.0, places=4)
        self.assertAlmostEqual(order.amount_untaxed, 216.0, places=2)

    def test_packaging_rule_fallback_to_standard(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        order = self._order()
        other_pack = self._line(order, qty=6, packaging=self.pack_6)
        no_pack = self._line(order, qty=5, packaging=False)
        self.assertFalse(other_pack.pricelist_item_id)
        self.assertFalse(no_pack.pricelist_item_id)
        self.assertAlmostEqual(other_pack.price_unit, 10.0, places=6)
        self.assertAlmostEqual(no_pack.price_unit, 10.0, places=6)

    def test_auto_suggested_packaging_is_priced(self):
        """Odoo suggests the biggest packaging dividing the quantity: the
        packaging price must follow."""
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        line = self._line(self._order(), qty=48)  # no explicit packaging
        self.assertEqual(line.product_packaging_id, self.carton)
        self.assertAlmostEqual(line.price_unit, 9.0, places=6)
        self.assertAlmostEqual(line.price_subtotal, 432.0, places=2)

    def test_packaging_priority_over_generic_rule_any_creation_order(self):
        for first_packaging in (True, False):
            pricelist = self._create_pricelist('Prio %s' % first_packaging)
            rules = [
                dict(packaging_id=self.carton.id, fixed_price=216.0),
                dict(fixed_price=9.5),
            ]
            if not first_packaging:
                rules.reverse()
            for vals in rules:
                self._product_item(pricelist, **vals)
            order = self._order(pricelist)
            carton_line = self._line(order, qty=24, packaging=self.carton)
            unit_line = self._line(order, qty=5, packaging=False)
            self.assertAlmostEqual(carton_line.price_unit, 9.0, places=6)
            self.assertAlmostEqual(unit_line.price_unit, 9.5, places=6)

    def test_packaging_min_quantity_counts_packages(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=200.0, min_quantity=2)
        order = self._order()
        one_carton = self._line(order, qty=24, packaging=self.carton)
        two_cartons = self._line(order, qty=48, packaging=self.carton)
        self.assertFalse(one_carton.pricelist_item_id)
        self.assertAlmostEqual(one_carton.price_unit, 10.0, places=6)
        self.assertAlmostEqual(two_cartons.price_unit, 200.0 / 24, places=6)
        self.assertAlmostEqual(two_cartons.price_subtotal, 400.0, places=2)

    def test_tiered_packaging_prices(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        self._product_item(packaging_id=self.carton.id, fixed_price=204.0, min_quantity=10)
        order = self._order()
        small = self._line(order, qty=24 * 3, packaging=self.carton)
        big = self._line(order, qty=24 * 10, packaging=self.carton)
        self.assertAlmostEqual(small.price_unit, 9.0, places=6)
        self.assertAlmostEqual(big.price_unit, 8.5, places=6)

    def test_variant_packaging_rule_beats_template_rule(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=230.0)
        self._item(applied_on='0_product_variant', product_id=self.product.id,
                   product_tmpl_id=self.tmpl.id, packaging_id=self.carton.id, fixed_price=216.0)
        line = self._line(self._order(), qty=24, packaging=self.carton)
        self.assertAlmostEqual(line.price_unit, 9.0, places=6)

    def test_packaging_of_other_product_never_matches(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=1.0)
        line = self._line(self._order(), product=self.juice, qty=12, packaging=self.juice_carton)
        self.assertFalse(line.pricelist_item_id)
        self.assertAlmostEqual(line.price_unit, 5.0, places=6)

    def test_packaging_line_in_other_uom(self):
        """Carton price must be converted to the line UoM (Dozens)."""
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        line = self._line(self._order(), qty=2, uom=self.uom_dozen, packaging=self.carton)
        self.assertAlmostEqual(line.price_unit, 108.0, places=6)
        self.assertAlmostEqual(line.price_subtotal, 216.0, places=2)
        self.assertAlmostEqual(line.asp_package_price, 216.0, places=4)

    # --------------------------------------------------------------- uom
    def test_uom_fixed_price(self):
        self._product_item(fixed_price=9.5)
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        order = self._order()
        dozen_line = self._line(order, qty=2, uom=self.uom_dozen, packaging=False)
        unit_line = self._line(order, qty=5, packaging=False)
        self.assertEqual(dozen_line.pricelist_item_id.uom_id, self.uom_dozen)
        self.assertAlmostEqual(dozen_line.price_unit, 100.0, places=6)
        self.assertAlmostEqual(dozen_line.price_subtotal, 200.0, places=2)
        self.assertAlmostEqual(unit_line.price_unit, 9.5, places=6)

    def test_standard_uom_conversion_kept_without_uom_rule(self):
        self._product_item(fixed_price=9.5)
        line = self._line(self._order(), qty=2, uom=self.uom_dozen, packaging=False)
        self.assertAlmostEqual(line.price_unit, 114.0, places=6)

    def test_uom_min_quantity_counts_rule_uom(self):
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0, min_quantity=5)
        order = self._order()
        four = self._line(order, qty=4, uom=self.uom_dozen, packaging=False)
        five = self._line(order, qty=5, uom=self.uom_dozen, packaging=False)
        self.assertAlmostEqual(four.price_unit, 120.0, places=6)
        self.assertAlmostEqual(five.price_unit, 100.0, places=6)

    def test_uom_rule_equal_to_product_uom(self):
        """A rule targeting the product's own UoM behaves as a generic rule for it."""
        self._product_item(uom_id=self.uom_unit.id, fixed_price=8.0)
        order = self._order()
        unit_line = self._line(order, qty=5, packaging=False)
        dozen_line = self._line(order, qty=1, uom=self.uom_dozen, packaging=False)
        self.assertAlmostEqual(unit_line.price_unit, 8.0, places=6)
        self.assertAlmostEqual(dozen_line.price_unit, 120.0, places=6)

    def test_line_price_reacts_to_uom_and_packaging_change(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        line = self._line(self._order(), qty=5, packaging=False)
        self.assertAlmostEqual(line.price_unit, 10.0, places=6)
        line.write({'product_uom_qty': 24, 'product_packaging_id': self.carton.id})
        self.assertAlmostEqual(line.price_unit, 9.0, places=6)
        line.write({'product_uom': self.uom_dozen.id, 'product_uom_qty': 2, 'product_packaging_id': False})
        self.assertAlmostEqual(line.price_unit, 100.0, places=6)
        self.assertAlmostEqual(line.order_id.amount_untaxed, 200.0, places=2)

    # --------------------------------------------------------------- API
    def test_pricelist_api_with_packaging_and_uom(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        pl = self.pricelist
        self.assertAlmostEqual(self._price(pl, self.product, 24, packaging=self.carton), 9.0, places=6)
        self.assertAlmostEqual(self._price(pl, self.product, 24, packaging=self.carton.id), 9.0, places=6)
        self.assertAlmostEqual(self._price(pl, self.product, 24), 10.0, places=6)
        self.assertAlmostEqual(self._price(pl, self.product, 2, uom=self.uom_dozen), 100.0, places=6)
        # product.template records are supported as well
        self.assertAlmostEqual(self._price(pl, self.tmpl, 24, packaging=self.carton), 9.0, places=6)
        # context-based packaging (used for chained pricelists)
        self.assertAlmostEqual(
            pl.with_context(asp_packaging_id=self.carton.id)._get_product_price(self.product, 24), 9.0, places=6)

    def test_multi_product_call(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        prices = self.pricelist._compute_price_rule(self.product | self.juice, 24, packaging=self.carton)
        self.assertAlmostEqual(prices[self.product.id][0], 9.0, places=6)
        self.assertAlmostEqual(prices[self.juice.id][0], 5.0, places=6)

    # -------------------------------------------------------- precision
    def test_rounding_gap_reported_with_low_precision(self):
        self.env.ref('product.decimal_price').digits = 2
        self._product_item(packaging_id=self.carton.id, fixed_price=200.0)
        line = self._line(self._order(), qty=24, packaging=self.carton)
        self.assertAlmostEqual(line.price_unit, 8.33, places=2)
        self.assertAlmostEqual(line._asp_price_rounding_gap(), 0.08, places=2)
        self.assertTrue(line._asp_rounding_warning())

    def test_no_rounding_gap_with_enough_precision(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=200.0)
        line = self._line(self._order(), qty=24, packaging=self.carton)
        self.assertAlmostEqual(line.price_subtotal, 200.0, places=2)
        self.assertEqual(line._asp_price_rounding_gap(), 0.0)
