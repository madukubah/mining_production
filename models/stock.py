# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ritase_order_id = fields.Many2one("production.ritase.order", related='move_lines.ritase_order_id',
        string="Ritase", readonly=True)

class StockMove(models.Model):
    _inherit = 'stock.move'

    ritase_order_id = fields.Many2one("production.ritase.order",
        'Ritase', ondelete='set null', index=True, readonly=True)
    
    production_order_id = fields.Many2one("production.order",
        'Production Order', ondelete='set null')