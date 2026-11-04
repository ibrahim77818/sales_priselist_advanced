# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from .common import AspCommon


@tagged('post_install', '-at_install', 'asp')
class TestConstraints(AspCommon):

    def test_uom_and_packaging_are_exclusive(self):
        with self.assertRaises(ValidationError):
            self._product_item(uom_id=self.uom_dozen.id, packaging_id=self.carton.id, fixed_price=1)

    def test_packaging_requires_product_scope(self):
        category_rule = self._item(applied_on='2_product_category', categ_id=self.categ_drinks.id, fixed_price=1)
        with self.assertRaises(ValidationError):
            category_rule.write({'packaging_id': self.carton.id})
        # created on a category scope: the packaging is dropped like product fields are
        rule = self._item(applied_on='2_product_category', categ_id=self.categ_drinks.id, fixed_price=1,
                          packaging_id=self.carton.id)
        self.assertFalse(rule.packaging_id)

    def test_switching_scope_to_global_drops_packaging(self):
        rule = self._product_item(packaging_id=self.carton.id, fixed_price=1)
        rule.write({'applied_on': '3_global'})
        self.assertFalse(rule.packaging_id)
        self.assertEqual(rule.asp_target, '2_any')

    def test_packaging_must_belong_to_template(self):
        with self.assertRaises(ValidationError):
            self._product_item(packaging_id=self.juice_carton.id, fixed_price=1)

    def test_packaging_must_belong_to_variant(self):
        with self.assertRaises(ValidationError):
            self._item(applied_on='0_product_variant', product_id=self.juice.id,
                       packaging_id=self.carton.id, fixed_price=1)

    def test_uom_category_must_match_product(self):
        with self.assertRaises(ValidationError):
            self._product_item(uom_id=self.uom_kg.id, fixed_price=1)
        # category / global rules accept any UoM
        rule = self._item(applied_on='3_global', uom_id=self.uom_kg.id, fixed_price=1)
        self.assertEqual(rule.asp_target, '1_uom')

    def test_deleting_packaging_removes_its_rules(self):
        rule = self._product_item(packaging_id=self.pack_6.id, fixed_price=50)
        self.pack_6.unlink()
        self.assertFalse(rule.exists())

    def test_allowed_targets(self):
        rule = self._product_item(fixed_price=1)
        self.assertIn(self.uom_dozen, rule.asp_allowed_uom_ids)
        self.assertNotIn(self.uom_kg, rule.asp_allowed_uom_ids)
        self.assertEqual(rule.asp_allowed_packaging_ids, self.pack_6 | self.carton)
        global_rule = self._item(applied_on='3_global', fixed_price=1)
        self.assertIn(self.uom_kg, global_rule.asp_allowed_uom_ids)
        self.assertFalse(global_rule.asp_allowed_packaging_ids)


@tagged('post_install', '-at_install', 'asp')
class TestPricelistModesUI(AspCommon):
    """Create rules through the real Odoo 18 views (pricelist form -> rule form)."""

    def test_rule_form_product_rules(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.display_applied_on = '1_product'
            item.product_tmpl_id = self.tmpl
            item.packaging_id = self.carton
            item.fixed_price = 216.0
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.uom_id = self.uom_dozen
            item.fixed_price = 100.0
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.uom_id = self.uom_dozen
            item.fixed_price = 99.0
            item.min_quantity = 10
            # UoM and packaging are mutually exclusive in the UI
            self.assertTrue(item._get_modifier('packaging_id', 'readonly'))
        form.save()
        rules = self.pricelist.item_ids
        self.assertEqual(set(rules.mapped('applied_on')), {'1_product'})
        self.assertEqual(sorted(rules.mapped('asp_target')), ['0_packaging', '1_uom', '1_uom'])

        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=24, packaging=self.carton).price_unit, 9.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=1, uom=self.uom_dozen, packaging=False).price_unit, 100.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=10, uom=self.uom_dozen, packaging=False).price_unit, 99.0, places=6)

    def test_rule_form_formula_and_global_rules(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.packaging_id = self.carton
            item.compute_price = 'formula'
            item.price_discount = 10
        with form.item_ids.new() as item:
            # no product nor category: global rule
            item.uom_id = self.uom_dozen
            item.compute_price = 'percentage'
            item.percent_price = 5
            self.assertTrue(item._get_modifier('packaging_id', 'invisible'))
        with form.item_ids.new() as item:
            item.display_applied_on = '2_product_category'
            item.categ_id = self.categ_food
            item.uom_id = self.uom_dozen
            item.fixed_price = 40.0
        form.save()
        self.assertEqual(sorted(self.pricelist.item_ids.mapped('applied_on')),
                         ['1_product', '2_product_category', '3_global'])
        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=24, packaging=self.carton).price_unit, 9.0, places=6)
        self.assertAlmostEqual(
            self._line(order, product=self.juice, qty=1, uom=self.uom_dozen, packaging=False).price_unit,
            57.0, places=6)
        self.assertAlmostEqual(self._line(order, product=self.egg_tray, qty=1).price_unit, 40.0, places=6)

    def test_rule_form_cost_markup_with_percent_fee(self):
        """The 'cost + markup + % fee' set-up (Odoo 18 shows a Markup field for cost-based rules)."""
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.packaging_id = self.pack_6
            item.compute_price = 'formula'
            item.base = 'standard_price'
            item.price_markup = 50
            item.price_surcharge_percent = 10
        form.save()
        rule = self.pricelist.item_ids
        self.assertAlmostEqual(rule.price_discount, -50.0)
        # pack of 6: cost 36 + 50 % = 54, + 10 % of 36 = 57.6 -> 9.6 per unit
        self.assertAlmostEqual(self._line(self._order(), qty=6, packaging=self.pack_6).price_unit, 9.6, places=6)

    def test_rule_form_scope_change_clears_packaging(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.packaging_id = self.carton
            item.product_tmpl_id = self.juice.product_tmpl_id
            self.assertFalse(item.packaging_id)
            item.fixed_price = 1.0

    def test_rule_form_switch_to_category_clears_targets(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.packaging_id = self.carton
            item.display_applied_on = '2_product_category'
            self.assertFalse(item.packaging_id)
            item.categ_id = self.categ_drinks
            item.fixed_price = 1.0
        form.save()
        self.assertEqual(self.pricelist.item_ids.applied_on, '2_product_category')

    def test_settings_view(self):
        settings = Form(self.env['res.config.settings'])
        settings.asp_convert_qty_on_uom_change = False
        settings.asp_round_qty_to_packaging = False
        settings.save().execute()
        self.assertFalse(self.company.asp_convert_qty_on_uom_change)
        self.assertFalse(self.company.asp_round_qty_to_packaging)


@tagged('post_install', '-at_install', 'asp')
class TestMarginConstraint(AspCommon):

    def test_min_margin_alone_is_allowed(self):
        rule = self._product_item(compute_price='formula', price_discount=50, price_min_margin=1.0)
        self.assertAlmostEqual(self._price(self.pricelist, self.product, 1), 11.0)
        self.assertTrue(rule)

    def test_min_above_max_still_rejected(self):
        with self.assertRaises(ValidationError):
            self._product_item(compute_price='formula', price_min_margin=5.0, price_max_margin=2.0)
