# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time

import logging
_logger = logging.getLogger(__name__)

class ProductionCopAdjust(models.Model):
    _name = "production.cop.adjust"
    
    READONLY_STATES = {
        'draft': [('readonly', False)],
        'confirm': [('readonly', True)],
        'done': [('readonly', True)],
        'cancel': [('readonly', True)],
    }

    name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
    date = fields.Date('Date', help='',default=time.strftime("%Y-%m-%d"), states=READONLY_STATES )
    employee_id	= fields.Many2one('hr.employee', string='Checker', states=READONLY_STATES )
    cost_ids = fields.One2many('fleet.vehicle.cost', 'cop_adjust_id', 'Vehicle Costs')

    state = fields.Selection([
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('done', 'Posted'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')
        
    @api.model
    def create(self, values):
        seq = self.env['ir.sequence'].next_by_code('cop_adjust')
        values["name"] = seq
        res = super(ProductionCopAdjust, self ).create(values)
        return res
    
    @api.multi
    def action_settle(self):
        for record in self:
            record.action_reload()
        self.state = 'confirm'

    @api.multi
    def action_reload(self):
        for record in self:
            record._reload()
    
    @api.multi
    def _reload(self):
        VehicleCost = self.env['fleet.vehicle.cost'].sudo()
        vehicle_costs = VehicleCost.search( [ ("date", "<=", self.date ), ("state", "=", "draft" ) ] )

        self.update({
            'cost_ids': [( 6, 0, vehicle_costs.ids )],
        })
        return True
