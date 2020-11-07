# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time
import datetime
from dateutil.relativedelta import relativedelta


class ProductionLosstime(models.Model):
    _name = "production.losstime"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    
    READONLY_STATES = {
        'draft': [('readonly', False)] ,
        'confirm': [('readonly', True)] ,
        'done': [('readonly', True)] ,
        'cancel': [('readonly', True)] ,
    }

    name = fields.Char(compute='_compute_name', store=True)
    date = fields.Date('Date', help='',  default=fields.Datetime.now, states=READONLY_STATES )
    shift = fields.Selection([
        ( "1" , '1'), 
        ( "2" , '2'),
        ], string='Shift', index=True, required=True, states=READONLY_STATES )
    losstime_type = fields.Selection([
		('slippery', 'Slippery'),
		('rainy', 'Rainy'),
        ], string='Losstime type', index=True, required=True, states=READONLY_STATES )
    vehicle_state_id = fields.Many2one('fleet.vehicle.state', string='Vehicle State', states=READONLY_STATES )
    tag_ids = fields.Many2many('fleet.vehicle.tag', 'production_losstime_vehicle_tag_rel', 'losstime_tag_id', 'tag_id', 'Tags', states=READONLY_STATES)
    vehicle_ids = fields.Many2many('fleet.vehicle', 'production_losstime_vehicle_rel', 'losstime_id', 'vehicle_id', 'Vehicles', copy=False, states=READONLY_STATES)
    start_datetime = fields.Datetime('Start Date Time', help='',  default=fields.Datetime.now, states=READONLY_STATES )
    end_datetime = fields.Datetime('End Date Time', help='', states=READONLY_STATES )
    hour = fields.Float('Hours', readonly=True, compute="_compute_hour" )
    remarks = fields.Char( String="Remarks", store=True, states=READONLY_STATES )
    state = fields.Selection( [
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('done', 'Done'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')

    @api.depends( 'date')
    def _compute_name(self):
        for record in self:
            self.name = record.date
    
    @api.depends('start_datetime', 'end_datetime')
    def _compute_hour(self):
        for record in self:
            #compute end date
            if record.start_datetime and record.end_datetime :
                start = datetime.datetime.strptime(record.start_datetime, '%Y-%m-%d %H:%M:%S')
                ends = datetime.datetime.strptime(record.end_datetime, '%Y-%m-%d %H:%M:%S')
                diff = relativedelta(ends, start)
                record.hour = diff.hours

    @api.multi
    def action_reload(self):
        for record in self: 
            Vehicle = self.env['fleet.vehicle'].sudo()
            vehicles = Vehicle.search( [ ( "tag_ids", "in", record.tag_ids.ids ), ( "state_id", "=", record.vehicle_state_id.id ),  ( "driver_id", "!=", False ) ] )
            record.update({
                'vehicle_ids': [( 6, 0, vehicles.ids )],
            })
    
    @api.multi
    def action_confirm(self):
        for record in self: 
            record.action_reload( )
            record.state = "confirm"

    @api.multi
    def action_done(self):
        VehicleLosstime = self.env['fleet.vehicle.losstime'].sudo()
        for record in self: 
            for vehicle in record.vehicle_ids: 
                VehicleLosstime.create({
                    "name" : vehicle.name +" / "+ record.date,
                    "date" : record.date,
                    "vehicle_id" : vehicle.id,
                    "driver_id" : vehicle.driver_id.id,
                    "shift" : record.shift,
                    "losstime_type" : record.losstime_type,
                    "start_datetime" : record.start_datetime,
                    "end_datetime" : record.end_datetime,
                    "remarks" : record.remarks,
                })
            record.state = "done"
    
    @api.multi
    def action_draft(self):
        for record in self: 
            record.state = "draft"
    
    @api.multi
    def action_cancel(self):
        for record in self: 
            if record.state in ["done"] :
                raise UserError(_('Cannot canceling record which is in state \'%s\'.') %(record.state,))
            record.state = "cancel"

    @api.multi
    def unlink(self):
        for record in self:
            if record.state in ['confirm', "done"] :
                raise UserError(_('Cannot delete record which is in state \'%s\'.') %(record.state,))
        return super(ProductionLosstime, self).unlink()
            