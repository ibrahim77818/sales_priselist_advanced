# -*- coding: utf-8 -*-
{
    'name': 'Advanced Sales Pricelist (UoM & Packaging Pricing)',
    'version': '18.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Pricelist rules per Unit of Measure and Product Packaging, '
               'with quantity normalization on sales order lines.',
    'description': """
Advanced Sales Pricelist
========================
* Target pricelist rules to a specific Unit of Measure or Product Packaging.
* Fixed prices, extra fees and margins of targeted rules are expressed per
  that unit / per package, then converted to the order line unit price.
* Priority engine: packaging rules > UoM rules > generic rules, within the
  standard scope order (variant > product > category > global).
* Works with fixed prices, discounts and formulas, discounts shown on
  quotations (Discounts setting), chained and multi-currency pricelists.
* Formula rules: percentage extra fee (on the base or the discounted price)
  in addition to the fixed extra fee (also applied by the Point of Sale).
* Excel import templates (fixed prices or all rule types; pricelists with
  rules, or rules for existing pricelists) and a "Pricelist Rules" bulk-edit screen.
* Sales order lines: optional conversion of the quantity when the UoM changes
  and rounding up to whole packages when a packaging is selected.
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
