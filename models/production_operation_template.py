# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time

class ProductionOperationTemplate(models.Model):
    _name = "production.operation.template"
    
    name = fields.Char(compute='_compute_vehicle_log_name', store=True)
    date = fields.Date('Date', help='' )
    # date = fields.Date('Date', help='', default=time.strftime("%Y-%m-%d")  )
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True)
    cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict", required=True )
    block_id = fields.Many2one('production.block', string='Block', ondelete="restrict", required=True )
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    driver_id	= fields.Many2one('res.partner', string='Driver', required=True )
    
    @api.depends('vehicle_id', 'date')
    def _compute_vehicle_log_name(self):
        for record in self:
            name = record.vehicle_id.name
            if not name:
                name = record.date
            elif record.date:
                name += ' / ' + record.date
            self.name = name


