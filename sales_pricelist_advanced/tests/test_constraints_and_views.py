# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from .common import AspCommon


@tagged('post_install', '-at_install', 'asp')
class TestConstraints(AspCommon):

    def test_unit_must_be_convertible_into_product_unit(self):
        with self.assertRaises(ValidationError):
            self._product_item(uom_id=self.uom_kg.id, fixed_price=1)
        # category / global rules accept any unit
        rule = self._item(applied_on='3_global', uom_id=self.uom_kg.id, fixed_price=1)
        self.assertEqual(rule.asp_target, '1_uom')

    def test_variant_rule_unit_checked_against_variant(self):
        with self.assertRaises(ValidationError):
            self._item(applied_on='0_product_variant', product_id=self.flour.id, uom_id=self.carton.id,
                       fixed_price=1)

    def test_switching_scope_keeps_compatible_unit(self):
        rule = self._product_item(uom_id=self.carton.id, fixed_price=1)
        rule.write({'applied_on': '3_global'})
        self.assertEqual(rule.uom_id, self.carton)
        self.assertEqual(rule.asp_target, '1_uom')

    def test_deleting_packaging_unit_removes_its_rules(self):
        box = self.env['uom.uom'].create({'name': 'ASP Box of 3', 'relative_factor': 3,
                                          'relative_uom_id': self.uom_unit.id})
        self.product.uom_ids |= box
        rule = self._product_item(uom_id=box.id, fixed_price=25)
        self.product.uom_ids -= box
        box.unlink()
        self.assertFalse(rule.exists())

    def test_allowed_units(self):
        rule = self._product_item(fixed_price=1)
        self.assertEqual(rule.asp_allowed_uom_ids, self.uom_unit | self.pack_6 | self.carton | self.uom_dozen)
        self.assertNotIn(self.uom_kg, rule.asp_allowed_uom_ids)
        global_rule = self._item(applied_on='3_global', fixed_price=1)
        self.assertIn(self.uom_kg, global_rule.asp_allowed_uom_ids)
        self.assertIn(self.carton, global_rule.asp_allowed_uom_ids)


@tagged('post_install', '-at_install', 'asp')
class TestPricelistModesUI(AspCommon):
    """Create rules through the real Odoo 18 views (pricelist form -> rule form)."""

    def test_rule_form_product_rules(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.display_applied_on = '1_product'
            item.product_tmpl_id = self.tmpl
            item.uom_id = self.carton
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
        form.save()
        rules = self.pricelist.item_ids
        self.assertEqual(set(rules.mapped('applied_on')), {'1_product'})
        self.assertEqual(set(rules.mapped('asp_target')), {'1_uom'})

        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=1, uom=self.carton).price_unit, 216.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=1, uom=self.uom_dozen).price_unit, 100.0, places=6)
        self.assertAlmostEqual(self._line(order, qty=10, uom=self.uom_dozen).price_unit, 99.0, places=6)

    def test_rule_form_formula_and_global_rules(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.uom_id = self.carton
            item.compute_price = 'formula'
            item.price_discount = 10
        with form.item_ids.new() as item:
            # no product nor category: global rule
            item.uom_id = self.uom_dozen
            item.compute_price = 'percentage'
            item.percent_price = 5
        with form.item_ids.new() as item:
            item.display_applied_on = '2_product_category'
            item.categ_id = self.categ_food
            item.uom_id = self.uom_dozen
            item.fixed_price = 40.0
        form.save()
        self.assertEqual(sorted(self.pricelist.item_ids.mapped('applied_on')),
                         ['1_product', '2_product_category', '3_global'])
        order = self._order()
        self.assertAlmostEqual(self._line(order, qty=1, uom=self.carton).price_unit, 216.0, places=6)
        self.assertAlmostEqual(
            self._line(order, product=self.juice, qty=1, uom=self.uom_dozen).price_unit, 57.0, places=6)
        self.assertAlmostEqual(self._line(order, product=self.egg_tray, qty=1).price_unit, 40.0, places=6)

    def test_rule_form_cost_markup_with_percent_fee(self):
        """The 'cost + markup + % fee' set-up (Odoo 18 shows a Markup field for cost-based rules)."""
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.uom_id = self.pack_6
            item.compute_price = 'formula'
            item.base = 'standard_price'
            item.price_markup = 50
            item.price_surcharge_percent = 10
        form.save()
        rule = self.pricelist.item_ids
        self.assertAlmostEqual(rule.price_discount, -50.0)
        # pack of 6: cost 36 + 50 % = 54, + 10 % of 36 = 57.6 per pack
        self.assertAlmostEqual(self._line(self._order(), qty=1, uom=self.pack_6).price_unit, 57.6, places=6)

    def test_rule_form_scope_change_clears_packaging(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.uom_id = self.carton
            item.product_tmpl_id = self.juice.product_tmpl_id
            self.assertFalse(item.uom_id)  # not a packaging of the juice
            item.fixed_price = 1.0

    def test_rule_form_switch_to_category_clears_targets(self):
        form = Form(self.pricelist)
        with form.item_ids.new() as item:
            item.product_tmpl_id = self.tmpl
            item.uom_id = self.carton
            item.display_applied_on = '2_product_category'
            item.categ_id = self.categ_drinks
            item.uom_id = self.carton  # any unit can be chosen on a category rule
            item.fixed_price = 1.0
        form.save()
        self.assertEqual(self.pricelist.item_ids.applied_on, '2_product_category')
        self.assertEqual(self.pricelist.item_ids.uom_id, self.carton)

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
