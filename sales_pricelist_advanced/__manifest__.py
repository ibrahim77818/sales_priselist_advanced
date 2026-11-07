# -*- coding: utf-8 -*-
{
    'name': 'Advanced Sales Pricelist (UoM & Packaging Pricing)',
    'version': '20.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Pricelist rules per unit and per packaging (Carton, Pack of 6, Dozen), '
               'percentage extra fees, Excel bulk import and quantity conversion on sales orders.',
    'description': """
Advanced Sales Pricelist
========================
* Target pricelist rules to a specific unit or packaging (in Odoo 20 a
  packaging such as "Carton of 24" is a unit of the product).
* Fixed prices, extra fees, margins and minimum quantities of these rules are
  expressed per that unit / per package.
* Priority engine: unit / packaging rules > generic rules, within the
  standard scope order (variant > product > category > global).
* Works with fixed prices, discounts and surcharges, discounts shown on
  quotations (Discounts setting), chained and multi-currency pricelists.
* Discount and surcharge rules: percentage extra fee (on the base or the discounted price)
  in addition to the fixed extra fee (also applied by the Point of Sale).
* Excel import templates (fixed prices or all rule types; pricelists with
  rules, or rules for existing pricelists) and a "Pricelist Rules" bulk-edit screen.
* Sales order lines: optional conversion of the quantity when the unit or
  packaging changes, rounded up to whole packages.
* Full Arabic (ar_001) translation, RTL-safe views.
""",
    'author': 'Ibrahim Yahia',
    'website': 'https://www.linkedin.com/in/ibrahim-yahia',
    'license': 'LGPL-3',
    'depends': ['sale', 'base_import'],
    'data': [
        'views/product_pricelist_item_views.xml',
        'views/product_pricelist_views.xml',
        'views/product_pricelist_item_menus.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
