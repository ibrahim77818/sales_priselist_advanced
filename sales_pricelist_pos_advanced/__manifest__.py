# -*- coding: utf-8 -*-
{
    'name': 'Advanced Sales Pricelist - Point of Sale bridge',
    'version': '19.0.1.1.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Companion of Advanced Sales Pricelist: percentage extra fees in the POS, '
               'UoM / packaging rules kept for quotations. Installed automatically.',
    'description': """
The Odoo 19 Point of Sale evaluates pricelist rules in the browser and does not
know about the Unit of Measure / Packaging conditions added by
"Advanced Sales Pricelist". Without this bridge, a rule such as
"Carton of 24 = 216.00" would be applied by the POS as 216.00 per unit.
This module (installed automatically):
* only sends generic rules (no UoM / packaging condition) to the POS,
* adds the percentage extra fee of formula rules to the POS price engine.
""",
    'author': 'Ibrahim Yahia',
    'website': 'https://www.linkedin.com/in/ibrahim-yahia',
    'license': 'LGPL-3',
    'depends': ['sales_pricelist_advanced', 'point_of_sale'],
    'data': [],
    'images': ['static/description/banner.png'],
    'assets': {
        'point_of_sale._assets_pos': [
            'sales_pricelist_pos_advanced/static/src/**/*',
        ],
        'web.assets_tests': [
            'sales_pricelist_pos_advanced/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'auto_install': True,
}
