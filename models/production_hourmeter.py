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
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True, required=True, states=READONLY_STATES )
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

    @api.multi
    def button_confirm(self):
        for order in self:
            for hourmeter_log in order.vehicle_hourmeter_log_ids:
                Hourmeter = self.env['fleet.vehicle.hourmeter'].sudo()
                hourmeter = Hourmeter.create({
                    'date' : hourmeter_log.date,
                    'vehicle_id' : hourmeter_log.vehicle_id.id,
                    'start' : hourmeter_log.start,
                    'end' : hourmeter_log.end,
                })

                hourmeter_log.write({ 'hourmeter_id' : hourmeter.id })
        self.write({ 'state' : 'confirm' })
    
    @api.multi
    def button_cancel(self):
        for order in self:
            for hourmeter_log in order.vehicle_hourmeter_log_ids:
                if hourmeter_log.hourmeter_id:
                    raise UserError(_('Unable to cancel order %s as some receptions have already been done.') % (order.name))

        self.write({'state': 'cancel'})
                
	
class ProductionVehicleHourmeterLog(models.Model):
    _name = "production.vehicle.hourmeter.log"
    _inherits = {'production.operation.template': 'operation_template_id'}

    hourmeter_order_id = fields.Many2one("production.hourmeter.order", string="Hourmeter Order", ondelete="set null" )
    hourmeter_id = fields.Many2one('fleet.vehicle.hourmeter', 'Hourmeter', help='Odometer measure of the vehicle at the moment of this log')
    date = fields.Date('Date', help='', related="hourmeter_order_id.date", readonly=True, default=time.strftime("%Y-%m-%d") )
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', readonly=True, index=True, related="hourmeter_order_id.shift", )

    start = fields.Float('Start Hour')
    end = fields.Float('End Hour')
    value = fields.Float('Hourmeter Value', group_operator="max", readonly=True, compute="_compute_value" )
    
    @api.depends('start', 'end')
    def _compute_value(self):
        for record in self:
            record.value = record.end - record.start
        