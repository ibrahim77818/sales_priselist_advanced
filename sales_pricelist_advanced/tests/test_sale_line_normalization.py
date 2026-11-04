# -*- coding: utf-8 -*-
"""Interactive behaviour of sales order lines (onchanges through the real form view)."""
from odoo.tests import Form, tagged

from .common import AspCommon

ONCHANGE_LOGGER = 'odoo.tests.common.onchange'


@tagged('post_install', '-at_install', 'asp')
class TestSaleLineNormalization(AspCommon):

    def _form(self, pricelist=None):
        form = Form(self.env['sale.order'])
        form.partner_id = self.partner
        form.pricelist_id = pricelist or self.pricelist
        return form

    # --------------------------------------------------------- UoM
    def test_uom_change_converts_quantity(self):
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 24
            line.product_uom = self.uom_dozen
            self.assertEqual(line.product_uom_qty, 2.0)
            self.assertAlmostEqual(line.price_unit, 120.0, places=6)
            line.product_uom = self.uom_unit
            self.assertEqual(line.product_uom_qty, 24.0)
        order = form.save()
        self.assertAlmostEqual(order.amount_untaxed, 240.0, places=2)
        self.assertEqual(order.order_line.asp_qty_uom_id, self.uom_unit)

    def test_uom_change_without_setting_keeps_number(self):
        self.company.asp_convert_qty_on_uom_change = False
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 24
            line.product_uom = self.uom_dozen
            self.assertEqual(line.product_uom_qty, 24.0)

    def test_uom_change_rounding_warning(self):
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 25
            with self.assertLogs(ONCHANGE_LOGGER, level='WARNING'):
                line.product_uom = self.uom_dozen
            self.assertEqual(line.product_uom_qty, 2.08)

    def test_uom_change_never_zeroes_quantity(self):
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 0.04
            line.product_uom = self.uom_dozen
            self.assertEqual(line.product_uom_qty, 0.04)

    def test_product_change_does_not_convert(self):
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 24
            line.product_id = self.egg_tray  # sold in Dozens
            self.assertEqual(line.product_uom, self.uom_dozen)
            self.assertEqual(line.product_uom_qty, 24.0)

    def test_saved_line_uses_stored_uom(self):
        """Line created through the ORM (no tracker): the stored UoM is the reference."""
        order = self._order()
        self._line(order, qty=36, packaging=False)
        form = Form(order)
        with form.order_line.edit(0) as line:
            line.product_uom = self.uom_dozen
            self.assertEqual(line.product_uom_qty, 3.0)
        form.save()
        self.assertEqual(order.order_line.product_uom, self.uom_dozen)
        self.assertEqual(order.order_line.product_uom_qty, 3.0)

    def test_api_write_keeps_standard_behaviour(self):
        order = self._order()
        line = self._line(order, qty=24, packaging=False)
        line.write({'asp_qty_uom_id': self.uom_unit.id, 'asp_qty_product_id': self.product.id})
        line.write({'product_uom': self.uom_dozen.id})
        self.assertEqual(line.product_uom_qty, 24.0)
        self.assertFalse(line.asp_qty_uom_id)
        self.assertFalse(line.asp_qty_product_id)

    # ---------------------------------------------------- packaging
    def test_packaging_selection_rounds_up(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 30
            line.product_packaging_id = self.carton
            self.assertEqual(line.product_uom_qty, 48.0)
            self.assertEqual(line.product_packaging_qty, 2.0)
            self.assertAlmostEqual(line.price_unit, 9.0, places=6)
        order = form.save()
        self.assertAlmostEqual(order.amount_untaxed, 432.0, places=2)

    def test_packaging_selection_from_default_quantity(self):
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_packaging_id = self.carton
            self.assertEqual(line.product_uom_qty, 24.0)

    def test_packaging_selection_without_setting(self):
        self.company.asp_round_qty_to_packaging = False
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_uom_qty = 30
            with self.assertLogs(ONCHANGE_LOGGER, level='WARNING'):  # standard Odoo warning
                line.product_packaging_id = self.carton
            self.assertEqual(line.product_uom_qty, 30.0)

    def test_packaging_qty_edit_updates_price_and_totals(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        self._product_item(packaging_id=self.carton.id, fixed_price=192.0, min_quantity=5)
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_packaging_id = self.carton
            line.product_packaging_qty = 5
            self.assertEqual(line.product_uom_qty, 120.0)
            self.assertAlmostEqual(line.price_unit, 8.0, places=6)
        order = form.save()
        self.assertAlmostEqual(order.amount_untaxed, 960.0, places=2)

    def test_uom_change_with_packaging_keeps_physical_qty_and_price(self):
        self._product_item(packaging_id=self.carton.id, fixed_price=216.0)
        form = self._form()
        with form.order_line.new() as line:
            line.product_id = self.product
            line.product_packaging_id = self.carton
            line.product_uom = self.uom_dozen
            self.assertEqual(line.product_uom_qty, 2.0)
            self.assertEqual(line.product_packaging_id, self.carton)
            self.assertAlmostEqual(line.price_unit, 108.0, places=6)
        order = form.save()
        self.assertAlmostEqual(order.amount_untaxed, 216.0, places=2)
