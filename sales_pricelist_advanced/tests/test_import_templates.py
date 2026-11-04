# -*- coding: utf-8 -*-
"""The shipped Excel templates are imported through Odoo's real importer
(base_import), exactly as an end user would, and the resulting prices are
checked. Any change to the templates or the import path is caught here."""
import io

from openpyxl import Workbook

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tools import file_open

from .common import AspCommon

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
TEMPLATE_DIR = 'sales_pricelist_advanced/static/xls/'


@tagged('post_install', '-at_install', 'asp')
class TestImportTemplates(AspCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env.user.groups_id |= env.ref('product.group_product_variant')
        cls.saleable = env.ref('product.product_category_1')
        env.ref('base.USD').active = True

        # Master data referenced by the example rows of the templates
        cls.water = cls._create_product('Water Bottle 1.5L', 1.0, cost=0.60, categ=cls.saleable)
        cls.water.default_code = 'WB15'
        cls.w_pack6 = cls._create_packaging(cls.water, 'Pack of 6', 6)
        cls.w_carton = cls._create_packaging(cls.water, 'Carton of 24', 24)
        cls.juice1l = cls._create_product('Orange Juice 1L', 2.0, categ=cls.saleable)
        cls.juice1l.default_code = 'OJ1'
        cls.j_carton = cls._create_packaging(cls.juice1l, 'Carton of 24', 24)

        color = env['product.attribute'].create({'name': 'ASP Color', 'value_ids': [
            Command.create({'name': 'Red'}), Command.create({'name': 'Blue'})]})
        size = env['product.attribute'].create({'name': 'ASP Size', 'value_ids': [
            Command.create({'name': 'L'}), Command.create({'name': 'M'})]})
        cls.tshirt = env['product.template'].create({
            'name': 'T-Shirt', 'list_price': 20.0, 'categ_id': cls.saleable.id, 'taxes_id': [Command.clear()],
            'attribute_line_ids': [
                Command.create({'attribute_id': color.id, 'value_ids': [Command.set(color.value_ids.ids)]}),
                Command.create({'attribute_id': size.id, 'value_ids': [Command.set(size.value_ids.ids)]}),
            ],
        })
        variants = cls.tshirt.product_variant_ids
        cls.red_l = variants.filtered(lambda v: set(v.product_template_attribute_value_ids.mapped('name')) == {'Red', 'L'})
        cls.blue_m = variants.filtered(lambda v: set(v.product_template_attribute_value_ids.mapped('name')) == {'Blue', 'M'})
        cls.red_l.default_code = 'TSH-RED-L'
        cls.other_product = cls._create_product('ASP Other', 10.0, categ=env.ref('product.product_category_all'))

        cls.retail = cls._create_pricelist('Retail')
        cls.wholesale = cls._create_pricelist('Wholesale')
        cls.distributor = cls._create_pricelist('Distributor')
        # Odoo 18 has no 'product.list0': companies get a pricelist named 'Default'.
        cls.public = env['product.pricelist'].search([('name', '=', 'Default')], limit=1) \
            or cls._create_pricelist('Default')
        cls.december = fields.Datetime.from_string('2026-12-15 12:00:00')

    # ------------------------------------------------------------------ helpers
    def _read_template(self, filename):
        with file_open(TEMPLATE_DIR + filename, 'rb') as f:
            return f.read()

    def _import(self, model, content, filename='import.xlsx', lang=None):
        importer = self.env['base_import.import'].with_context(lang=lang).create({
            'res_model': model, 'file': content, 'file_name': filename, 'file_type': XLSX,
        })
        options = {'has_headers': True, 'quoting': '"', 'separator': ',', 'limit': 2000,
                   'float_thousand_separator': ',', 'float_decimal_separator': '.', 'advanced': True}
        preview = importer.parse_preview(dict(options))
        self.assertNotIn('error', preview, preview.get('error'))
        headers = preview['headers']
        # every column must be auto-mapped (no manual mapping for the end user)
        matches = preview['matches'] or {}
        mapped = {headers[int(i)]: '/'.join(path) for i, path in matches.items()}
        self.assertEqual(mapped, {h: h for h in headers}, "all template columns must map automatically")
        result = importer.execute_import(headers, headers, dict(options, sheet=preview['options']['sheet']))
        return result

    def _assert_ok(self, result):
        errors = [m for m in result['messages'] if m.get('type') == 'error']
        self.assertFalse(errors, errors)
        return result['ids']

    def _p(self, pricelist, product, qty=1, **kw):
        return pricelist._get_product_price(product, qty, **kw)

    # ------------------------------------------------------------- registry
    def test_templates_are_offered_in_import_screen(self):
        pl_templates = [t['template'] for t in self.env['product.pricelist'].get_import_templates()]
        item_templates = [t['template'] for t in self.env['product.pricelist.item'].get_import_templates()]
        self.assertIn('/product/static/xls/product_pricelist.xls', pl_templates)
        for path in pl_templates[1:] + item_templates:
            self.assertTrue(path.startswith('/sales_pricelist_advanced/static/xls/'))
            self.assertTrue(self._read_template(path.rsplit('/', 1)[1]))
        self.assertEqual(len(pl_templates), 3)
        self.assertEqual(len(item_templates), 2)

    def test_headers_map_in_arabic(self):
        self.env['res.lang']._activate_lang('ar_001')
        result = self._import('product.pricelist.item', self._read_template('asp_pricelist_rules_advanced.xlsx'),
                              lang='ar_001')
        self.assertEqual(len(self._assert_ok(result)), 12)

    # ------------------------------------------- rules: fixed prices
    def test_import_rules_basic(self):
        ids = self._assert_ok(self._import('product.pricelist.item', self._read_template('asp_pricelist_rules_basic.xlsx')))
        self.assertEqual(len(ids), 9)
        rules = self.env['product.pricelist.item'].browse(ids)
        self.assertEqual(rules.pricelist_id, self.retail)
        self.assertEqual(set(rules.mapped('compute_price')), {'fixed'})
        # packaging resolved per product although "Carton of 24" exists twice
        juice_rule = rules.filtered(lambda r: r.product_tmpl_id == self.juice1l.product_tmpl_id)
        self.assertEqual(juice_rule.packaging_id, self.j_carton)
        variant_rule = rules.filtered('product_id')
        self.assertEqual(variant_rule.applied_on, '0_product_variant')
        self.assertEqual(variant_rule.product_tmpl_id, self.tshirt)  # template filled automatically

        pl, w, dozen = self.retail, self.water, self.uom_dozen
        self.assertAlmostEqual(self._p(pl, w), 1.20)
        self.assertAlmostEqual(self._p(pl, w, 50), 1.10)
        self.assertAlmostEqual(self._p(pl, w, 1, uom=dozen), 13.00)
        self.assertAlmostEqual(self._p(pl, w, 6, packaging=self.w_pack6), 1.10)
        self.assertAlmostEqual(self._p(pl, w, 24, packaging=self.w_carton) * 24, 25.00)
        self.assertAlmostEqual(self._p(pl, w, 240, packaging=self.w_carton) * 24, 24.00)
        self.assertAlmostEqual(self._p(pl, self.juice1l, 24, packaging=self.j_carton) * 24, 40.00)
        self.assertAlmostEqual(self._p(pl, self.red_l), 15.00)
        self.assertAlmostEqual(self._p(pl, self.blue_m), 20.00)
        self.assertAlmostEqual(self._p(pl, w, 1, date=self.december), 0.99)

    # ------------------------------------------- rules: all rule types
    def test_import_rules_advanced(self):
        ids = self._assert_ok(self._import('product.pricelist.item', self._read_template('asp_pricelist_rules_advanced.xlsx')))
        self.assertEqual(len(ids), 12)
        rules = self.env['product.pricelist.item'].browse(ids)
        self.assertEqual(rules.pricelist_id, self.wholesale | self.distributor)
        self.assertEqual(set(rules.mapped('applied_on')), {'3_global', '2_product_category', '1_product', '0_product_variant'})
        self.assertEqual(set(rules.mapped('compute_price')), {'fixed', 'percentage', 'formula'})
        self.assertEqual(set(rules.mapped('base')), {'list_price', 'standard_price', 'pricelist'})
        self.assertEqual(set(rules.mapped('price_surcharge_percent_base')), {'base', 'discounted'})

        pl, w = self.wholesale, self.water
        # product rules beat category / global rules
        self.assertAlmostEqual(self._p(pl, w), 1.15)
        self.assertAlmostEqual(self._p(pl, w, 100), 0.88)
        # per Dozen: 12 -8% = 11.04 + 2% of 12 = 11.28
        self.assertAlmostEqual(self._p(pl, w, 1, uom=self.uom_dozen), 11.28)
        self.assertAlmostEqual(self._p(pl, w, 24, packaging=self.w_carton) * 24, 24.00)
        # 10+ cartons: cost 14.40 + 0.50 + 20% (2.88) = 17.78
        self.assertAlmostEqual(self._p(pl, w, 240, packaging=self.w_carton) * 24, 17.78)
        # juice carton: 48 -15% = 40.80 (rounded 0.05) + 3% of 40.80 = 42.024
        self.assertAlmostEqual(self._p(pl, self.juice1l, 24, packaging=self.j_carton) * 24, 42.024)
        self.assertAlmostEqual(self._p(pl, self.red_l), 14.00)
        # category formula: 20 -10% = 18 -> rounded 18 -> -0.01
        self.assertAlmostEqual(self._p(pl, self.blue_m), 17.99)
        # category UoM rule (Dozens, -4%) for the variant sold by the dozen
        self.assertAlmostEqual(self._p(pl, self.blue_m, 1, uom=self.uom_dozen), 230.40)
        # global rule for products outside the category
        self.assertAlmostEqual(self._p(pl, self.other_product), 9.50)
        # December promotion (-20 % on the product)
        self.assertAlmostEqual(self._p(pl, w, 1, date=self.december), 0.80)
        # other pricelist row: 3% below Retail (no Retail rule -> list price)
        self.assertAlmostEqual(self._p(self.distributor, self.other_product), 9.70)

    # -------------------------------------- pricelists: fixed prices
    def test_import_pricelists_basic(self):
        ids = self._assert_ok(self._import('product.pricelist', self._read_template('asp_pricelists_basic.xlsx')))
        pricelists = self.env['product.pricelist'].browse(ids)
        self.assertEqual(pricelists.mapped('name'), ['Retail', 'Export USD'])
        retail, export = pricelists
        self.assertEqual(len(retail.item_ids), 6)
        self.assertEqual(len(export.item_ids), 4)
        self.assertEqual(retail.currency_id, self.company.currency_id)
        self.assertEqual(export.currency_id, self.env.ref('base.USD'))
        self.assertEqual(export.country_group_ids, self.env.ref('base.europe'))
        self.assertEqual(export.item_ids.filtered(lambda r: r.product_tmpl_id == self.juice1l.product_tmpl_id).packaging_id,
                         self.j_carton)
        self.assertAlmostEqual(self._p(retail, self.water, 240, packaging=self.w_carton) * 24, 24.00)
        self.assertAlmostEqual(self._p(export, self.water, 24, packaging=self.w_carton) * 24, 33.00)
        self.assertAlmostEqual(self._p(export, self.red_l, 1, uom=self.uom_dozen), 170.00)

    # ------------------------------------ pricelists: all rule types
    def test_import_pricelists_advanced(self):
        ids = self._assert_ok(self._import('product.pricelist', self._read_template('asp_pricelists_advanced.xlsx')))
        pricelists = self.env['product.pricelist'].browse(ids)
        self.assertEqual(pricelists.mapped('name'), ['Retail', 'Wholesale USD'])
        retail, wholesale = pricelists
        self.assertEqual(len(retail.item_ids), 8)
        self.assertEqual(len(wholesale.item_ids), 3)
        chained = wholesale.item_ids.filtered(lambda r: r.base == 'pricelist')
        self.assertEqual(chained.base_pricelist_id, self.public)
        self.assertEqual(chained.price_surcharge_percent_base, 'discounted')
        self.assertAlmostEqual(self._p(retail, self.water, 1, uom=self.uom_dozen), 11.28)
        # USD = 1 (no rate) -> other product: 10 -10% = 9 + 2% of 9 = 9.18
        self.env['res.currency.rate'].search([('currency_id', '=', self.env.ref('base.USD').id)]).unlink()
        self.env['res.currency.rate'].search([('currency_id', '=', self.company.currency_id.id)]).unlink()
        self.assertAlmostEqual(self._p(wholesale, self.other_product), 9.18)
        # carton from 5: cost 0.60 * 24 = 14.40, -(-25 %) = 18.00, rounded to 0.5
        self.assertAlmostEqual(self._p(wholesale, self.water, 120, packaging=self.w_carton) * 24, 18.00)

    # ------------------------------------------------------- error report
    def _xlsx(self, rows):
        wb = Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_import_unknown_packaging_is_reported(self):
        content = self._xlsx([
            ['pricelist_id', 'product_tmpl_id', 'packaging_id', 'fixed_price'],
            ['Retail', 'WB15', 'Pallet of 500', 400],
        ])
        importer = self.env['base_import.import'].create({
            'res_model': 'product.pricelist.item', 'file': content, 'file_name': 'x.xlsx', 'file_type': XLSX})
        result = importer.execute_import(['pricelist_id', 'product_tmpl_id', 'packaging_id', 'fixed_price'],
                                         ['pricelist_id', 'product_tmpl_id', 'packaging_id', 'fixed_price'],
                                         {'has_headers': True, 'quoting': '"', 'separator': ','})
        self.assertTrue([m for m in result['messages'] if m['type'] == 'error'])
        self.assertFalse(self.retail.item_ids)

    def test_import_packaging_of_other_product_only_is_rejected(self):
        """Packaging name that exists only on another product: clear error, no silent mapping."""
        content = self._xlsx([
            ['pricelist_id', 'product_tmpl_id', 'packaging_id', 'fixed_price'],
            ['Retail', 'OJ1', 'Pack of 6', 10],
        ])
        importer = self.env['base_import.import'].create({
            'res_model': 'product.pricelist.item', 'file': content, 'file_name': 'x.xlsx', 'file_type': XLSX})
        cols = ['pricelist_id', 'product_tmpl_id', 'packaging_id', 'fixed_price']
        result = importer.execute_import(cols, cols, {'has_headers': True, 'quoting': '"', 'separator': ','})
        errors = [m for m in result['messages'] if m['type'] == 'error']
        self.assertTrue(errors)
        self.assertIn('Pack of 6', errors[0]['message'])

    def _run(self, rows):
        content = self._xlsx(rows)
        importer = self.env['base_import.import'].create({
            'res_model': 'product.pricelist.item', 'file': content, 'file_name': 'x.xlsx', 'file_type': XLSX})
        return importer.execute_import(rows[0], rows[0], {'has_headers': True, 'quoting': '"', 'separator': ','})

    def test_packaging_name_unknown_for_product(self):
        result = self._run([
            ['pricelist_id', 'product_tmpl_id', 'packaging_name', 'fixed_price'],
            ['Retail', 'OJ1', 'Pack of 6', 10],
        ])
        errors = [m for m in result['messages'] if m['type'] == 'error']
        self.assertTrue(errors)
        self.assertIn('Pack of 6', errors[0]['message'])
        self.assertFalse(self.retail.item_ids)

    def test_packaging_name_case_insensitive_and_blank(self):
        ids = self._assert_ok(self._run([
            ['pricelist_id', 'product_tmpl_id', 'packaging_name', 'fixed_price'],
            ['Retail', 'OJ1', 'carton OF 24', 40],
            ['Retail', 'WB15', '', 1.2],
        ]))
        rules = self.env['product.pricelist.item'].browse(ids)
        self.assertEqual(rules[0].packaging_id, self.j_carton)
        self.assertFalse(rules[1].packaging_id)

    def test_packaging_name_on_category_rule_rejected(self):
        result = self._run([
            ['pricelist_id', 'applied_on', 'categ_id', 'packaging_name', 'compute_price', 'percent_price'],
            ['Retail', 'Product Category', 'All / Saleable', 'Carton of 24', 'Discount', 5],
        ])
        self.assertTrue([m for m in result['messages'] if m['type'] == 'error'])

    def test_blank_cells_keep_defaults(self):
        ids = self._assert_ok(self._run([
            ['pricelist_id', 'applied_on', 'product_tmpl_id', 'compute_price', 'base',
             'price_discount', 'price_surcharge_percent', 'price_surcharge_percent_base', 'price_min_margin'],
            ['Retail', 'Product', 'WB15', 'Formula', '', 10, 5, '', 0.05],
        ]))
        rule = self.env['product.pricelist.item'].browse(ids)
        self.assertEqual(rule.base, 'list_price')
        self.assertEqual(rule.price_surcharge_percent_base, 'base')
        # 1.00 -10% + 5% of 1.00 = 0.95, min margin +0.05 -> at least 1.05
        self.assertAlmostEqual(self._p(self.retail, self.water), 1.05)

    def test_blank_pricelist_currency(self):
        pricelist = self.env['product.pricelist'].create({'name': 'Blank', 'currency_id': False})
        self.assertEqual(pricelist.currency_id, self.env.company.currency_id)
        pricelist.write({'currency_id': False, 'name': 'Renamed'})
        self.assertEqual(pricelist.name, 'Renamed')
        self.assertEqual(pricelist.currency_id, self.env.company.currency_id)

    def test_imported_category_rule_opens_as_category(self):
        ids = self._assert_ok(self._import('product.pricelist.item', self._xlsx([
            ['pricelist_id', 'applied_on', 'categ_id', 'compute_price', 'percent_price'],
            ['Retail', 'Product Category', 'All / Saleable', 'Discount', 5],
        ])))
        rule = self.env['product.pricelist.item'].browse(ids)
        self.assertEqual(rule.applied_on, '2_product_category')
        self.assertEqual(rule.display_applied_on, '2_product_category')
        rule.applied_on = '3_global'
        self.assertEqual(rule.display_applied_on, '1_product')
