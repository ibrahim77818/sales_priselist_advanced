# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    asp_convert_qty_on_uom_change = fields.Boolean(
        string="Keep Quantity on UoM Change",
        default=True,
        help="When the unit or packaging of a sales order line is changed, convert the "
             "quantity so that the physical quantity stays the same "
             "(e.g. 24 Units become 2 Dozens or 1 Carton of 24).")
    asp_round_qty_to_packaging = fields.Boolean(
        string="Round Up to Whole Packages",
        default=True,
        help="When a sales order line is sold in a packaging (e.g. Carton of 24), round its "
             "quantity up to a whole number of packages.")
