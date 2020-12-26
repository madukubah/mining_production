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
        string='Counters',
        copy=True, states=READONLY_STATES )

    state = fields.Selection( [
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('done', 'Done'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')
    
    @api.multi
    def unlink(self):
        for order in self:
            if order.state in ['confirm', "done"] :
                raise UserError(_('Cannot delete  order which is in state \'%s\'.') %(order.state,))
        return super(ProductionWatertruckOrder, self).unlink()
        
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
    def action_done( self ):
        for order in self:
            order.state = 'done'

    @api.multi
    def action_cancel(self):
        for order in self:
            for counter_id in order.counter_ids:
                if counter_id.state == 'posted' :
                    raise UserError(_('Unable to cancel order %s as some receptions have already been done.') % (order.name))

            order.write({'state': 'cancel'})

class ProductionWatertruckCounter(models.Model):
    _name = "production.watertruck.counter"

    WATERTRUCK_PRICE = {
        '6000': 7000 ,
        '8000': 10000 ,
        '16000': 21000 ,
    }

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
    capacity = fields.Selection([
        ( "6000" , '6000 L'),
        ( "8000" , '8000 L'),
        ( "16000" , '16000 L'),
        ], string='Capacity', index=True, required=True, default="6000" )
        
    driver_id	= fields.Many2one('res.partner', string='Driver', required=True )

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    log_ids = fields.One2many(
        'production.watertruck.log',
        'counter_id',
        string='Logs',
        copy=True )
    ritase_count = fields.Integer( string="Ritase Count", required=True, default=0, digits=0, compute='_compute_ritase_count' )
    amount = fields.Float(string='Amount', compute="_compute_amount", store=True )

    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )
    
    @api.depends( 'vehicle_id', 'date' )
    def _compute_name(self):
        for record in self:
            name = record.vehicle_id.name
            if not name:
                name = record.date
            elif record.date:
                name += ' / ' + record.date
            record.name = name

    @api.depends('ritase_count', 'capacity')
    def _compute_amount(self):
        for record in self:
            record.amount = record.ritase_count * ProductionWatertruckCounter.WATERTRUCK_PRICE[ record.capacity ]

    @api.multi
    def post(self):
        for record in self:
            if record.state != 'posted' and record.cop_adjust_id :
                self.env['production.cop.tag.log'].sudo().create({
                        'cop_adjust_id' : record.cop_adjust_id.id,
                        'name' :   'Water Truck / ' + record.date,
                        'date' : record.date,
                        'tag_id' : record.production_config_id.wt_tag_id.id,
                        'product_uom_qty' : record.ritase_count,
                        # 'price_unit' : record.amount /record.ritase_count,
                        'price_unit' : ProductionWatertruckCounter.WATERTRUCK_PRICE[ record.capacity ], # TODO : change it programable
                        'amount' : record.amount,
                        'state' : 'posted',
                    })
                record.write({'state' : 'posted' })

    @api.onchange('vehicle_id')	
    def _change_vehicle_id(self):
        for record in self:
            record.driver_id = record.vehicle_id.driver_id
    
    @api.depends('log_ids')	
    def _compute_ritase_count(self):
        for record in self:
            record.ritase_count = len( record.log_ids )

class WatertruckLog(models.Model):
	_name = "production.watertruck.log"

	counter_id = fields.Many2one("production.watertruck.counter", string="Dump Truck Activity", ondelete="cascade" )
	datetime = fields.Datetime('Date Time', help='',  default=time.strftime("%Y-%m-%d %H:%M:%S") )