# -*- coding: utf-8 -*-
"""Discount and formula rules per unit / packaging, priorities, chained pricelists."""
from odoo.tests import tagged

from .common import AspCommon


@tagged('post_install', '-at_install', 'asp')
class TestAdvancedPricing(AspCommon):

    # ------------------------------------------------------- formulas
    def test_packaging_formula_discount_round_surcharge(self):
        # Carton base = 240 -> -10% = 216 -> rounded to 1.0 = 216 -> -0.01 fee = 215.99 per carton
        self._product_item(uom_id=self.carton.id, compute_price='formula', base='list_price',
                           price_discount=10, price_round=1.0, price_surcharge=-0.01)
        line = self._line(self._order(), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 215.99, places=6)

    def test_packaging_formula_rounding_applies_to_package_price(self):
        # 240 * 0.93 = 223.2 -> rounding 5.0 per carton => 225.0 (not 9.3 rounded per unit)
        self._product_item(uom_id=self.carton.id, compute_price='formula', price_discount=7, price_round=5.0)
        line = self._line(self._order(), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 225.0, places=6)

    def test_standard_formula_rounding_without_packaging_rule(self):
        """Generic rule: Odoo rounds the price computed in the line unit (carton)."""
        self._product_item(compute_price='formula', price_discount=7, price_round=5.0)
        line = self._line(self._order(), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 225.0, places=6)

    def test_packaging_formula_margins_per_package(self):
        pl_min = self._create_pricelist('Min margin')
        self._product_item(pl_min, uom_id=self.carton.id, compute_price='formula',
                           price_discount=50, price_min_margin=-20)  # 120 -> at least 240-20 = 220
        pl_max = self._create_pricelist('Max margin')
        self._product_item(pl_max, uom_id=self.carton.id, compute_price='formula',
                           price_discount=-50, price_max_margin=30)  # 360 -> at most 240+30 = 270
        self.assertAlmostEqual(self._price(pl_min, self.product, 1, uom=self.carton), 220.0, places=6)
        self.assertAlmostEqual(self._price(pl_max, self.product, 1, uom=self.carton), 270.0, places=6)

    def test_packaging_formula_based_on_cost(self):
        # cost 6 -> 144 per carton + 6.0 fee per carton = 150
        self._product_item(uom_id=self.carton.id, compute_price='formula',
                           base='standard_price', price_surcharge=6.0)
        line = self._line(self._order(), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 150.0, places=6)

    def test_packaging_formula_markup_on_cost(self):
        # cost 144 per carton + 25 % markup = 180
        rule = self._product_item(uom_id=self.carton.id, compute_price='formula',
                                  base='standard_price', price_markup=25)
        self.assertAlmostEqual(rule.price_discount, -25.0)
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1, uom=self.carton), 180.0, places=6)

    def test_packaging_percentage(self):
        self._product_item(uom_id=self.carton.id, compute_price='percentage', percent_price=15)
        line = self._line(self._order(), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 204.0, places=6)

    def test_uom_formula_surcharge_per_rule_uom(self):
        # 120 per dozen -10% = 108 + 2.0 per dozen = 110
        self._product_item(uom_id=self.uom_dozen.id, compute_price='formula',
                           price_discount=10, price_surcharge=2.0)
        line = self._line(self._order(), qty=3, uom=self.uom_dozen)
        self.assertAlmostEqual(line.price_unit, 110.0, places=6)

    # ------------------------------------------------ global / category
    def test_global_uom_rule(self):
        self._item(applied_on='3_global', uom_id=self.uom_dozen.id,
                   compute_price='percentage', percent_price=5)
        order = self._order()
        water = self._line(order, qty=1, uom=self.uom_dozen)
        juice = self._line(order, product=self.juice, qty=1, uom=self.uom_dozen)
        units = self._line(order, qty=5)
        flour = self._line(order, product=self.flour, qty=2)
        self.assertAlmostEqual(water.price_unit, 114.0, places=6)
        self.assertAlmostEqual(juice.price_unit, 57.0, places=6)
        self.assertAlmostEqual(units.price_unit, 10.0, places=6)
        self.assertAlmostEqual(flour.price_unit, 3.0, places=6)

    def test_global_rule_unit_incompatible_with_product_never_matches(self):
        """A global rule per kg never applies to products counted in units."""
        self._item(applied_on='3_global', uom_id=self.uom_kg.id, fixed_price=1.0)
        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=2).price_unit, 10.0, places=6)
        self.assertAlmostEqual(self._line(order, product=self.flour, qty=2).price_unit, 1.0, places=6)

    def test_category_uom_rule(self):
        self._item(applied_on='2_product_category', categ_id=self.categ_drinks.id,
                   uom_id=self.uom_dozen.id, compute_price='percentage', percent_price=10)
        order = self._order()
        water = self._line(order, qty=1, uom=self.uom_dozen)
        eggs = self._line(order, product=self.egg_tray, qty=1)  # Food, sold in Dozens
        self.assertAlmostEqual(water.price_unit, 108.0, places=6)
        self.assertAlmostEqual(eggs.price_unit, 30.0, places=6)

    def test_scope_hierarchy_preserved(self):
        """A product-level generic rule still beats a category-level unit rule:
        targeting only breaks ties inside the same scope."""
        self._item(applied_on='2_product_category', categ_id=self.categ_drinks.id,
                   uom_id=self.uom_dozen.id, compute_price='percentage', percent_price=10)
        self._product_item(compute_price='percentage', percent_price=20)
        line = self._line(self._order(), qty=1, uom=self.uom_dozen)
        self.assertAlmostEqual(line.price_unit, 96.0, places=6)

    def test_targeted_rule_beats_generic_same_scope_despite_min_qty(self):
        self._product_item(compute_price='percentage', percent_price=30, min_quantity=24)
        self._product_item(uom_id=self.carton.id, compute_price='percentage', percent_price=10)
        line = self._line(self._order(), qty=2, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 216.0, places=6)

    def test_rule_order_puts_targeted_first(self):
        generic = self._product_item(fixed_price=9.0)
        uom_rule = self._product_item(uom_id=self.uom_dozen.id, fixed_price=100.0)
        pack_rule = self._product_item(uom_id=self.carton.id, fixed_price=200.0, min_quantity=2)
        ordered = self.env['product.pricelist.item'].search([('pricelist_id', '=', self.pricelist.id)])
        self.assertEqual(ordered.ids, [pack_rule.id, uom_rule.id, generic.id])
        self.assertEqual((pack_rule | uom_rule | generic).mapped('asp_target'), ['1_uom', '1_uom', '2_any'])

    # ------------------------------------------------ discount display
    # Odoo 18+ has no "discount policy": with the Discounts setting on, only
    # percentage rules show their discount on the order line.
    def test_percentage_packaging_rule_shows_discount(self):
        self._enable_discount_display()
        pricelist = self._create_pricelist('Show discount')
        self._product_item(pricelist, uom_id=self.carton.id, compute_price='percentage', percent_price=10)
        line = self._line(self._order(pricelist), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 240.0, places=6)
        self.assertAlmostEqual(line.discount, 10.0, places=4)
        self.assertAlmostEqual(line.price_subtotal, 216.0, places=2)

    def test_percentage_rule_without_discount_setting_is_net(self):
        pricelist = self._create_pricelist('Net percentage')
        self._product_item(pricelist, uom_id=self.carton.id, compute_price='percentage', percent_price=10)
        line = self._line(self._order(pricelist), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 216.0, places=6)
        self.assertAlmostEqual(line.discount, 0.0, places=4)

    def test_fixed_package_price_never_shows_discount(self):
        self._enable_discount_display()
        pricelist = self._create_pricelist('Fixed package')
        self._product_item(pricelist, uom_id=self.carton.id, fixed_price=180.0)
        line = self._line(self._order(pricelist), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 180.0, places=6)
        self.assertAlmostEqual(line.discount, 0.0, places=4)

    def test_percentage_uom_rule_shows_discount(self):
        self._enable_discount_display()
        pricelist = self._create_pricelist('Show discount uom')
        self._product_item(pricelist, uom_id=self.uom_dozen.id, compute_price='percentage', percent_price=25)
        line = self._line(self._order(pricelist), qty=1, uom=self.uom_dozen)
        self.assertAlmostEqual(line.price_unit, 120.0, places=6)
        self.assertAlmostEqual(line.discount, 25.0, places=4)
        self.assertAlmostEqual(line.price_subtotal, 90.0, places=2)

    def test_formula_surcharge_not_shown_as_discount(self):
        self._enable_discount_display()
        pricelist = self._create_pricelist('Surcharge')
        self._product_item(pricelist, uom_id=self.carton.id, compute_price='formula', price_surcharge=24.0)
        line = self._line(self._order(pricelist), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 264.0, places=6)
        self.assertAlmostEqual(line.discount, 0.0, places=4)

    # ------------------------------------------------ chained pricelists
    def test_chained_pricelist_propagates_unit(self):
        base_pl = self._create_pricelist('Base')
        self._product_item(base_pl, uom_id=self.carton.id, fixed_price=216.0)
        chained = self._create_pricelist('Chained')
        self._item(chained, applied_on='3_global', compute_price='formula', base='pricelist',
                   base_pricelist_id=base_pl.id, price_discount=10)
        order = self._order(chained)
        self.assertAlmostEqual(self._line(order, qty=1, uom=self.carton).price_unit, 194.4, places=6)
        self.assertAlmostEqual(self._line(order, qty=5).price_unit, 9.0, places=6)

    def test_chained_pricelist_targeted_on_both_levels(self):
        base_pl = self._create_pricelist('Base 2')
        self._product_item(base_pl, uom_id=self.carton.id, fixed_price=216.0)
        chained = self._create_pricelist('Chained 2')
        # -1.0 per carton on top of the base pricelist carton price
        self._product_item(chained, uom_id=self.carton.id, compute_price='formula', base='pricelist',
                           base_pricelist_id=base_pl.id, price_surcharge=-1.0)
        line = self._line(self._order(chained), qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 215.0, places=6)

    def test_chained_percentage_rules_show_cumulated_discount(self):
        self._enable_discount_display()
        base_pl = self._create_pricelist('Base 3')
        self._product_item(base_pl, uom_id=self.carton.id, compute_price='percentage', percent_price=10)
        chained = self._create_pricelist('Chained 3')
        self._item(chained, applied_on='3_global', compute_price='percentage', base='pricelist',
                   base_pricelist_id=base_pl.id, percent_price=10)
        line = self._line(self._order(chained), qty=1, uom=self.carton)
        # 240 list price -> carton rule -10 % -> chained -10 % = 194.4, shown as 19 % off 240
        self.assertAlmostEqual(line.price_unit, 240.0, places=6)
        self.assertAlmostEqual(line.discount, 19.0, places=4)
        self.assertAlmostEqual(line.price_subtotal, 194.4, places=2)

    # ------------------------------------------------ order level
    def test_update_prices_after_pricelist_change(self):
        target_pl = self._create_pricelist('Target')
        self._product_item(target_pl, uom_id=self.carton.id, fixed_price=216.0)
        order = self._order()
        line = self._line(order, qty=1, uom=self.carton)
        self.assertAlmostEqual(line.price_unit, 240.0, places=6)
        order.pricelist_id = target_pl
        order.action_update_prices()
        self.assertAlmostEqual(line.price_unit, 216.0, places=6)
        self.assertAlmostEqual(order.amount_untaxed, 216.0, places=2)

    def test_rule_display_name_and_price(self):
        rule = self._product_item(uom_id=self.carton.id, fixed_price=216.0)
        self.assertIn(self.carton.name, rule.name)
        self.assertIn(self.carton.name, rule.price)
        formula = self._product_item(uom_id=self.uom_dozen.id, compute_price='formula', price_discount=5)
        self.assertIn(self.uom_dozen.name, formula.name)
        self.assertIn(self.uom_dozen.name, formula.rule_tip)
