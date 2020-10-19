# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time


class ProductionLosstime(models.Model):
    _name = "production.losstime"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    
    name = fields.Char(compute='_compute_name', store=True)
    date = fields.Date('Date', help='',  default=fields.Datetime.now )
    # vehicle_id  = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    # cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict", required=True )
    # block_id = fields.Many2one('production.block', string='Block', ondelete="restrict", required=True )
    shift = fields.Selection([
        ( "1" , '1'), 
        ( "2" , '2'), 
        ], string='Shift', index=True, required=True )
    state = fields.Selection([
        # ('breakdown', 'Breakdown'), 
		('slippery', 'Slippery'),
		('rainy', 'Rainy'),
		# ('no_operator', 'No Operator'),
        ], string='Status', index=True, required=True )
    hour = fields.Float('Hours')
    remarks = fields.Char( String="Remarks", store=True)

    @api.depends( 'date')
    def _compute_name(self):
        for record in self:
            # name = record.vehicle_id.name
            # if not name:
            #     name = record.date
            # elif record.date:
            #     name += ' / ' + record.date
            self.name = record.date

