# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
# import time
import datetime
from dateutil.relativedelta import relativedelta

import logging
_logger = logging.getLogger(__name__)

class ProductionHourmeterOrder(models.Model):
    _name = "production.hourmeter.order"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = "date desc"
    
    READONLY_STATES = {
        'draft': [('readonly', False)] ,
        'confirm': [('readonly', True)] ,
        # 'done': [('readonly', True)] ,
        'cancel': [('readonly', True)] ,
    }

    name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
    employee_id	= fields.Many2one('hr.employee', string='Checker',required=True, states=READONLY_STATES )
    date = fields.Date('Date', help='',  default=fields.Datetime.now, states=READONLY_STATES )

    location_id = fields.Many2one(
            'stock.location', 'Location',
			domain=[ ('usage','=',"internal")  ],
            ondelete="restrict" )
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    driver_id	= fields.Many2one('res.partner', string='Driver' )

    # start = fields.Float('Start Hour')
    # end = fields.Float('End Hour')
    # hours = fields.Float('Hour (World Clock)', group_operator="max", readonly=True, compute="_compute_minutes", store=True )
    # value = fields.Float('Hourmeter Value', group_operator="max", readonly=True, compute="_compute_value", store=True )

    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], default='1', string='Shift', index=True, required=True, states=READONLY_STATES )
    vehicle_hourmeter_log_ids = fields.One2many(
        'production.vehicle.hourmeter.log',
        'hourmeter_order_id',
        string='HE Hourmeter',
        copy=False, states=READONLY_STATES )
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
        return super(ProductionHourmeterOrder, self).unlink()

    @api.depends('start', 'end')
    def _compute_value(self):
        for record in self:
            record.value = record.end - record.start

    @api.onchange('vehicle_id')	
    def _change_vehicle_id(self):
        for record in self:
            record.driver_id = record.vehicle_id.driver_id

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
                hourmeter_log._compute_amount()
                Hourmeter = self.env['fleet.vehicle.hourmeter'].sudo()
                hourmeter = Hourmeter.create({
                    'date' : hourmeter_log.date,
                    'vehicle_id' : hourmeter_log.vehicle_id.id,
                    'start' : hourmeter_log.start,
                    'end' : hourmeter_log.end,
                    'remarks' : hourmeter_log.cost_code_id.name if hourmeter_log.cost_code_id else " " ,
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
    _order = "driver_id asc ,start_datetime asc"
    # _inherits = {'production.operation.template': 'operation_template_id'}

    @api.model
    def _default_config(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0]

    
    name = fields.Char(compute='_compute_name', store=True)
    production_config_id = fields.Many2one('production.config', string='Config', default=_default_config)

    hourmeter_order_id = fields.Many2one("production.hourmeter.order", string="Hourmeter Order", ondelete="cascade" )
    hourmeter_id = fields.Many2one('fleet.vehicle.hourmeter', 'Hourmeter', help='Odometer measure of the vehicle at the moment of this log')
    date = fields.Date('Date', help='', related="hourmeter_order_id.date", readonly=True, default=fields.Datetime.now, store=True )
    shift = fields.Selection( [
        ( "1" , '1'),
        ( "2" , '2')],
        # related="hourmeter_order_id.shift", 
        # default=_default_shift,
        string='Shift', index=True, required=True, store=True )
    location_id = fields.Many2one(
            'stock.location', 'Location',
            # default=hourmeter_order_id.location_id,
            # related="hourmeter_order_id.location_id",
			domain=[ ('usage','=',"internal")  ],
            store=True,
            ondelete="restrict" )

    start_datetime = fields.Datetime('Start Date Time', help='', store=True )
    end_datetime = fields.Datetime('End Date Time', help='' , store=True)
    hours = fields.Float('Hours', readonly=True, compute="_compute_value", store=True )

    start = fields.Float('Start Hour')
    end = fields.Float('End Hour')
    value = fields.Float('Hourmeter Value', group_operator="max", readonly=True, compute="_compute_value", store=True )

    amount = fields.Float(string='Amount', compute="_compute_amount", store=True )

    cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict" )
    block_id = fields.Many2one('production.block', string='Block', ondelete="restrict")

    vehicle_id = fields.Many2one('fleet.vehicle',  string='Vehicle',  related="hourmeter_order_id.vehicle_id", required=True, store=True )
    driver_id	= fields.Many2one('res.partner', 
                    string='Driver', 
                    # default=hourmeter_order_id.driver_id,
                    # related="hourmeter_order_id.driver_id", 
                    required=True, store=True )

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )


    @api.onchange( 'hourmeter_order_id' )
    def _change_hourmeter_order_id(self):
        for record in self:
            record.shift = record.hourmeter_order_id.shift
            record.location_id = record.hourmeter_order_id.location_id
            record.driver_id = record.hourmeter_order_id.driver_id

    @api.onchange( 'date' )
    def _set_date(self):
        for record in self:
            record.start_datetime = record.date
            record.end_datetime = record.date

    @api.onchange('start_datetime', 'end_datetime')
    def _compute_minutes(self):
        for record in self:
            if record.start_datetime and record.end_datetime :
                start = datetime.datetime.strptime(record.start_datetime, '%Y-%m-%d %H:%M:%S')
                ends = datetime.datetime.strptime(record.end_datetime, '%Y-%m-%d %H:%M:%S')
                diff = relativedelta(ends, start)
                record.minutes = diff.minutes + ( diff.hours * 60 )
                record.hours = diff.hours


    @api.depends( 'vehicle_id', 'date' )
    def _compute_name(self):
        for record in self:
            name = record.vehicle_id.name
            if not name:
                name = record.date
            elif record.date:
                name += ' / ' + record.date
            record.name = name
    
    @api.onchange('vehicle_id')	
    def _change_vehicle_id(self):
        for record in self:
            record.driver_id = record.vehicle_id.driver_id

    @api.depends('start', 'end')
    def _compute_value(self):
        for record in self:
            record.value = record.end - record.start
            if record.start_datetime and record.end_datetime :
                start = datetime.datetime.strptime(record.start_datetime, '%Y-%m-%d %H:%M:%S')
                ends = datetime.datetime.strptime(record.end_datetime, '%Y-%m-%d %H:%M:%S')
                diff = relativedelta(ends, start)

                record.hours = diff.hours

    @api.depends('value')	
    def _compute_amount(self):
        for record in self:
            # for employee commisions we using world clock house
            # record.amount = record.hours * record.production_config_id.hm_price_unit
            record.amount = record.value * record.production_config_id.hm_price_unit

    @api.multi
    def post(self):
        '''
        for compute ore cost of production
        '''
        for record in self:
            if record.state != 'posted' and record.cop_adjust_id :
                self.env['production.cop.tag.log'].sudo().create({
                        # 'cop_adjust_id' : record.cop_adjust_id.id,
                        'name' :   'HM / ' + record.date,
                        'date' : record.date,
                        'location_id' : record.location_id.id,
                        'tag_id' : record.production_config_id.hm_tag_id.id,
                        'product_uom_qty' : record.value,
                        # 'price_unit' : record.amount /record.value,
                        'price_unit' : record.production_config_id.hm_price_unit, # TODO : change it programable
                        'amount' : record.amount,
                        'state' : 'posted',
                        'from_cop_adjust' : True,
                    })
                record.write({'state' : 'posted' })
            else :
                raise UserError(_('Hourmeter Error') )
