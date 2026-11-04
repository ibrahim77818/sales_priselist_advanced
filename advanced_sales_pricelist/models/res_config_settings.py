# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    asp_convert_qty_on_uom_change = fields.Boolean(
        related='company_id.asp_convert_qty_on_uom_change', readonly=False)
    asp_round_qty_to_packaging = fields.Boolean(
        related='company_id.asp_round_qty_to_packaging', readonly=False)
