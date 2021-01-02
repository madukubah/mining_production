# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time

class ProductionHourmeterOrder(models.Model):
    _name = "production.hourmeter.order"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = "id desc"
    
    READONLY_STATES = {
        'draft': [('readonly', False)] ,
        'confirm': [('readonly', True)] ,
        'done': [('readonly', True)] ,
        'cancel': [('readonly', True)] ,
    }

    name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
    employee_id	= fields.Many2one('hr.employee', string='Checker',required=True, states=READONLY_STATES )
    date = fields.Date('Date', help='',  default=fields.Datetime.now, states=READONLY_STATES )
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True, required=True, states=READONLY_STATES )
    vehicle_hourmeter_log_ids = fields.One2many(
        'production.vehicle.hourmeter.log',
        'hourmeter_order_id',
        string='HE Hourmeter',
        copy=True, states=READONLY_STATES )
    state = fields.Selection( [
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('done', 'Done'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')

    @api.model
    def create(self, values):
        seq = self.env['ir.sequence'].next_by_code('hourmeter')
        values["name"] = seq
        res = super(ProductionHourmeterOrder, self ).create(values)
        return res

    @api.multi
    def action_draft(self):
        for order in self:
            order.write({'state': 'draft'})

    @api.multi
    def action_done(self):
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
                # hourmeter_log.post()
            order.write({'state': 'done'})
        
    @api.multi
    def action_confirm(self):
        for order in self:
            order.write({ 'state' : 'confirm' })
    
    @api.multi
    def action_cancel(self):
        for order in self:
            for hourmeter_log in order.vehicle_hourmeter_log_ids:
                if hourmeter_log.hourmeter_id:
                    raise UserError(_('Unable to cancel order %s as some receptions have already been done.') % (order.name))

            order.write({'state': 'cancel'})
                
class ProductionVehicleHourmeterLog(models.Model):
    _name = "production.vehicle.hourmeter.log"
    _inherits = {'production.operation.template': 'operation_template_id'}

    hourmeter_order_id = fields.Many2one("production.hourmeter.order", string="Hourmeter Order", ondelete="restrict" )
    hourmeter_id = fields.Many2one('fleet.vehicle.hourmeter', 'Hourmeter', help='Odometer measure of the vehicle at the moment of this log')
    date = fields.Date('Date', help='', related="hourmeter_order_id.date", readonly=True, default=fields.Datetime.now )
    shift = fields.Selection( [
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True, related="hourmeter_order_id.shift" )

    start = fields.Float('Start Hour')
    end = fields.Float('End Hour')
    value = fields.Float('Hourmeter Value', group_operator="max", readonly=True, compute="_compute_value", store=True )
    amount = fields.Float(string='Amount', compute="_compute_amount", store=True )
    
    @api.onchange('vehicle_id')	
    def _change_vehicle_id(self):
        for record in self:
            record.driver_id = record.vehicle_id.driver_id

    @api.depends('start', 'end')
    def _compute_value(self):
        for record in self:
            record.value = record.end - record.start

    @api.depends('value')	
    def _compute_amount(self):
        for record in self:
            record.amount = record.value * record.production_config_id.hm_price_unit

    @api.multi
    def post(self):
        '''
        for compute ore cost of production
        '''
        for record in self:
            if record.state != 'posted' and record.cop_adjust_id :
                self.env['production.cop.tag.log'].sudo().create({
                        'cop_adjust_id' : record.cop_adjust_id.id,
                        'name' :   'HM / ' + record.date,
                        'date' : record.date,
                        'location_id' : record.location_id.id,
                        'tag_id' : record.production_config_id.hm_tag_id.id,
                        'product_uom_qty' : record.value,
                        # 'price_unit' : record.amount /record.value,
                        'price_unit' : record.production_config_id.hm_price_unit, # TODO : change it programable
                        'amount' : record.amount,
                        'state' : 'posted',
                    })
                record.write({'state' : 'posted' })
        