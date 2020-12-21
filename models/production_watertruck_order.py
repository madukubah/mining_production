# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time

class ProductionWatertruckOrder(models.Model):
    _name = "production.watertruck.order"
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
    
    counter_ids = fields.One2many(
        'production.watertruck.counter',
        'order_id',
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
        seq = self.env['ir.sequence'].next_by_code('watertruck')
        values["name"] = seq
        res = super(ProductionWatertruckOrder, self ).create(values)
        return res
    
    @api.multi
    def action_draft(self):
        for order in self:
            order.write({'state': 'draft'})
    
    @api.multi
    def action_confirm(self):
        for order in self:
            order.write({ 'state' : 'confirm' })
    
    @api.multi
    def action_cancel(self):
        for order in self:
            for counter_id in order.counter_ids:
                if counter_id.state == 'posted' :
                    raise UserError(_('Unable to cancel order %s as some receptions have already been done.') % (order.name))

            order.write({'state': 'cancel'})

class ProductionWatertruckCounter(models.Model):
    _name = "production.watertruck.counter"

    @api.model
    def _default_config(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0]

    order_id = fields.Many2one("production.watertruck.order", string="Order", ondelete="restrict" )

    name = fields.Char(compute='_compute_name', store=True)
    production_config_id = fields.Many2one('production.config', string='Config', default=_default_config)
    date = fields.Date('Date', help='', related="order_id.date", readonly=True, default=fields.Datetime.now )
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True )
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    driver_id	= fields.Many2one('res.partner', string='Driver', required=True )

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    log_ids = fields.One2many(
        'production.watertruck.log',
        'counter_id',
        string='Logs',
        copy=True )

    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )
    
    @api.onchange('vehicle_id')	
    def _change_vehicle_id(self):
        for record in self:
            record.driver_id = record.vehicle_id.driver_id

class WatertruckLog(models.Model):
	_name = "production.watertruck.log"

	counter_id = fields.Many2one("production.watertruck.counter", string="Dump Truck Activity", ondelete="cascade" )
	datetime = fields.Datetime('Date Time', help='',  default=time.strftime("%Y-%m-%d %H:%M:%S") )