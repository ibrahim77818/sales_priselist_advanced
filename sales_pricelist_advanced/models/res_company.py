# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    asp_convert_qty_on_uom_change = fields.Boolean(
        string="Keep Quantity on UoM Change",
        default=True,
        help="When the unit of measure of a sales order line is changed, convert the "
             "quantity so that the physical quantity stays the same "
             "(e.g. 24 Units become 2 Dozens).")
    asp_round_qty_to_packaging = fields.Boolean(
        string="Round Up to Whole Packages",
        default=True,
        help="When a packaging is selected on a sales order line, round the quantity "
             "up to a whole number of packages.")
