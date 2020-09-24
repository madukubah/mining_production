# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time

class ProductionHourmeter(models.Model):
    _name = "production.hourmeter.order"
    
    READONLY_STATES = {
        'confirm': [('readonly', True)],
    }

    name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
    employee_id	= fields.Many2one('hr.employee', string='Checker', states=READONLY_STATES )
    date = fields.Date('Date', help='',  default=time.strftime("%Y-%m-%d"), states=READONLY_STATES )
    shift = fields.Integer( string="Shift", default=0, digits=0, states=READONLY_STATES)
    vehicle_hourmeter_log_ids = fields.One2many(
        'production.vehicle.hourmeter.log',
        'hourmeter_order_id',
        string='HE Hourmeter',
        copy=True, states=READONLY_STATES )
    state = fields.Selection([
        ('open', 'Open'), 
		('confirm', 'Confirmed'),
		('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='open')

    @api.model
    def create(self, values):
        seq = self.env['ir.sequence'].next_by_code('hourmeter')
        values["name"] = seq
        res = super(ProductionHourmeter, self ).create(values)
        return res

class ProductionVehicleHourmeterLog(models.Model):
    _name = "production.vehicle.hourmeter.log"

    hourmeter_order_id = fields.Many2one("production.hourmeter.order", string="Hourmeter Order", ondelete="restrict" )

    name = fields.Char(compute='_compute_vehicle_log_name', store=True)
    date = fields.Date('Date', help='', related="hourmeter_order_id.date", default=time.strftime("%Y-%m-%d")  )
    cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict", required=True )
    block_id = fields.Many2one('production.block', string='Block', ondelete="restrict", required=True )
    driver_id	= fields.Many2one('hr.employee', string='Driver', required=True )
    vehicle_id  = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    start = fields.Float('Start Hour')
    end = fields.Float('End Hour')
    value = fields.Float('Hourmeter Value', group_operator="max", readonly=True, compute="_compute_value" )
    # breakdown_hour = fields.Float('BD Hours')
    # slippery_hour = fields.Float('Slippery Hours')
    # rainy_hour = fields.Float('Rainy Hours')

    state = fields.Selection([
        ('open', 'Open'), 
		('confirm', 'Confirmed'),
		('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='open')

    @api.depends('vehicle_id', 'date')
    def _compute_vehicle_log_name(self):
        for record in self:
            name = record.vehicle_id.name
            if not name:
                name = record.date
            elif record.date:
                name += ' / ' + record.date
            self.name = name
    
    @api.depends('start', 'end')
    def _compute_value(self):
        for record in self:
            record.value = record.end - record.start