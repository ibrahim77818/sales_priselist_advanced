# -*- coding: utf-8 -*-
"""Fixed prices per unit and per packaging (Odoo 19: packagings are units)."""
from odoo.tests import tagged

from .common import AspCommon


@tagged('post_install', '-at_install', 'asp')
class TestBasicPricing(AspCommon):

    # ---------------------------------------------------------- packaging
    def test_packaging_fixed_price_on_order_line(self):
        self._product_item(uom_id=self.carton.id, fixed_price=216.0)
        order = self._order()
        line = self._line(order, qty=1, uom=self.carton)
        self.assertEqual(line.pricelist_item_id.uom_id, self.carton)
        self.assertAlmostEqual(line.price_unit, 216.0, places=6)
        self.assertAlmostEqual(order.amount_untaxed, 216.0, places=2)

    def test_standard_packaging_price_without_rule(self):
        """Without a packaging rule, Odoo 19 prices a carton at 24 x the unit price."""
        self._product_item(fixed_price=9.5)
        line = self._line(self._order(), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 228.0, places=6)

    def test_packaging_rule_fallback_to_standard(self):
        self._product_item(uom_id=self.carton.id, fixed_price=216.0)
        order = self._order()
        other_pack = self._line(order, qty=1, uom=self.pack_6)
        units = self._line(order, qty=5)
        self.assertFalse(other_pack.pricelist_item_id)
        self.assertFalse(units.pricelist_item_id)
        self.assertAlmostEqual(other_pack.price_unit, 60.0, places=6)
        self.assertAlmostEqual(units.price_unit, 10.0, places=6)

    def test_packaging_priority_over_generic_rule_any_creation_order(self):
        for first_packaging in (True, False):
            pricelist = self._create_pricelist('Prio %s' % first_packaging)
            rules = [dict(uom_id=self.carton.id, fixed_price=216.0), dict(fixed_price=9.5)]
            if not first_packaging:
                rules.reverse()
            for vals in rules:
                self._product_item(pricelist, **vals)
            order = self._order(pricelist)
            self.assertAlmostEqual(self._line(order, qty=1, uom=self.carton).price_unit, 216.0, places=6)
            self.assertAlmostEqual(self._line(order, qty=5).price_unit, 9.5, places=6)

    def test_packaging_min_quantity_counts_packages(self):
        self._product_item(uom_id=self.carton.id, fixed_price=200.0, min_quantity=2)
        order = self._order()
        one_carton = self._line(order, qty=1, uom=self.carton)
        two_cartons = self._line(order, qty=2, uom=self.carton)
        self.assertFalse(one_carton.pricelist_item_id)
        self.assertAlmostEqual(one_carton.price_unit, 240.0, places=6)
        self.assertAlmostEqual(two_cartons.price_unit, 200.0, places=6)
        self.assertAlmostEqual(two_cartons.price_subtotal, 400.0, places=2)

    def test_tiered_packaging_prices(self):
        self._product_item(uom_id=self.carton.id, fixed_price=216.0)
        self._product_item(uom_id=self.carton.id, fixed_price=204.0, min_quantity=10)
        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=3, uom=self.carton).price_unit, 216.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=10, uom=self.carton).price_unit, 204.0, places=6)

    def test_generic_min_quantity_still_counts_product_units(self):
        """A generic rule's min. quantity is in product units: 1 carton = 24 units."""
        self._product_item(fixed_price=9.0, min_quantity=24)
        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=1, uom=self.carton).price_unit, 216.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=3, uom=self.pack_6).price_unit, 60.0, places=6)

    def test_variant_packaging_rule_beats_template_rule(self):
        self._product_item(uom_id=self.carton.id, fixed_price=230.0)
        self._item(applied_on='0_product_variant', product_id=self.product.id,
                   product_tmpl_id=self.tmpl.id, uom_id=self.carton.id, fixed_price=216.0)
        line = self._line(self._order(), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 216.0, places=6)

    def test_packaging_rule_of_other_product_never_matches(self):
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=1.0)
        line = self._line(self._order(), product=self.juice, qty=1, uom=self.uom_dozen)
        self.assertFalse(line.pricelist_item_id)
        self.assertAlmostEqual(line.price_unit, 60.0, places=6)

    # --------------------------------------------------------------- uom
    def test_uom_fixed_price(self):
        self._product_item(fixed_price=9.5)
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        order = self._order()
        dozen_line = self._line(order, qty=2, uom=self.uom_dozen)
        unit_line = self._line(order, qty=5)
        self.assertEqual(dozen_line.pricelist_item_id.uom_id, self.uom_dozen)
        self.assertAlmostEqual(dozen_line.price_unit, 100.0, places=6)
        self.assertAlmostEqual(dozen_line.price_subtotal, 200.0, places=2)
        self.assertAlmostEqual(unit_line.price_unit, 9.5, places=6)

    def test_standard_uom_conversion_kept_without_uom_rule(self):
        self._product_item(fixed_price=9.5)
        line = self._line(self._order(), qty=2, uom=self.uom_dozen)
        self.assertAlmostEqual(line.price_unit, 114.0, places=6)

    def test_uom_min_quantity_counts_rule_uom(self):
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0, min_quantity=5)
        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=4, uom=self.uom_dozen).price_unit, 120.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=5, uom=self.uom_dozen).price_unit, 100.0, places=6)

    def test_uom_rule_equal_to_product_uom(self):
        """A rule targeting the product's own unit applies to that unit only."""
        self._product_item(uom_id=self.uom_unit.id, fixed_price=8.0)
        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=5).price_unit, 8.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=1, uom=self.uom_dozen).price_unit, 120.0, places=6)

    def test_product_sold_in_dozens_with_unit_packaging_rule(self):
        """Product whose own unit is Dozens: a rule per Dozen is its own unit."""
        self._product_item(product=self.egg_tray, uom_id=self.uom_dozen.id, fixed_price=27.0)
        line = self._line(self._order(), product=self.egg_tray, qty=2)
        self.assertAlmostEqual(line.price_unit, 27.0, places=6)

    def test_line_price_reacts_to_unit_change(self):
        self._product_item(uom_id=self.carton.id, fixed_price=216.0)
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        line = self._line(self._order(), qty=5)
        self.assertAlmostEqual(line.price_unit, 10.0, places=6)
        line.write({'product_uom_qty': 1, 'product_uom_id': self.carton.id})
        self.assertAlmostEqual(line.price_unit, 216.0, places=6)
        line.write({'product_uom_id': self.uom_dozen.id, 'product_uom_qty': 2})
        self.assertAlmostEqual(line.price_unit, 100.0, places=6)
        self.assertAlmostEqual(line.order_id.amount_untaxed, 200.0, places=2)

    # --------------------------------------------------------------- API
    def test_pricelist_api_with_units(self):
        self._product_item(uom_id=self.carton.id, fixed_price=216.0)
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        pl = self.pricelist
        self.assertAlmostEqual(self._price(pl, self.product, 1, uom=self.carton), 216.0, places=6)
        self.assertAlmostEqual(self._price(pl, self.product, 24), 10.0, places=6)
        self.assertAlmostEqual(self._price(pl, self.product, 2, uom=self.uom_dozen), 100.0, places=6)
        # product.template records are supported as well
        self.assertAlmostEqual(self._price(pl, self.tmpl, 1, uom=self.carton), 216.0, places=6)

    def test_multi_product_call(self):
        self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        prices = self.pricelist._compute_price_rule(self.product | self.juice, 1, uom=self.uom_dozen)
        self.assertAlmostEqual(prices[self.product.id][0], 100.0, places=6)
        self.assertAlmostEqual(prices[self.juice.id][0], 60.0, places=6)

    def test_unknown_caller_without_uom_ignores_unit_rules(self):
        """Engine called without a unit: rules for other units never match."""
        self._product_item(uom_id=self.carton.id, fixed_price=1.0)
        rules = self.pricelist._get_applicable_rules(self.product, False)
        self.assertFalse(rules)

    def test_exact_subtotal_for_uneven_package_price(self):
        """200.00 per carton of 24 sold by the unit: Odoo 19 keeps full precision."""
        self.env.ref('product.decimal_price').digits = 2
        self._product_item(uom_id=self.uom_unit.id, fixed_price=200.0 / 24)
        line = self._line(self._order(), qty=24)
        self.assertAlmostEqual(line.price_subtotal, 200.0, places=2)
