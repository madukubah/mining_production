 # -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
# import time
import datetime
from dateutil.relativedelta import relativedelta

import logging
_logger = logging.getLogger(__name__)

class ProductionDumptruckPerformance(models.Model):
	_name = "production.dumptruck.performance"
	_inherit = ['mail.thread', 'ir.needaction_mixin']

	READONLY_STATES = {
        'draft': [('readonly', False)] ,
        'confirm': [('readonly', True)] ,
        'done': [('readonly', True)] ,
        'cancel': [('readonly', True)] ,
    }
	name = fields.Char(compute='_compute_name', store=True)
	date = fields.Date('Date', help='',  default=fields.Datetime.now, states=READONLY_STATES )
	end_date = fields.Date('End Date', help='',  default=fields.Datetime.now, states=READONLY_STATES )
	vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
	log_ids = fields.Many2many('production.ritase.log', 'production_dumptruck_performance_log_rel', 'dumptruck_id', 'log_id', 'Logs', copy=False, states=READONLY_STATES)
	counter_ids = fields.Many2many('production.ritase.counter', 'production_dumptruck_performance_ritase_counter_rel', 'dumptruck_id', 'counter_id', 'Counters', copy=False, states=READONLY_STATES)
	vehicle_losstime_ids = fields.Many2many('fleet.vehicle.losstime', 'production_dumptruck_performance_losstime_rel', 'dumptruck_id', 'vehicle_losstime_id', 'Loss Time', copy=False, states=READONLY_STATES)

	availability = fields.Float('Minutes Availability')
	minutes = fields.Float('Working Minutes', readonly=True )
	breakdown = fields.Float('Breakdown Minutes', readonly=True, default=0 )
	standby = fields.Float('Standby Minutes', readonly=True, default=0 )

	physical_availability = fields.Float('Physical Availability (%)', readonly=True, default=0, compute="_compute_performance" )
	used_availability = fields.Float('Used Of Availability (%)', readonly=True, default=0, compute="_compute_performance" )
	mechanical_availability = fields.Float('Mechanical Availability (%)', readonly=True, default=0, compute="_compute_performance" )
	effective_utilization = fields.Float('Effective Utilization (%)', readonly=True, default=0, compute="_compute_performance" )


	state = fields.Selection( [
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('done', 'Done'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')

	@api.depends( 'vehicle_id', 'date' )
	def _compute_name(self):
		for record in self:
			name = record.vehicle_id.name
			if not name:
				name = record.date
			elif record.date:
				name += ' / ' + record.date
			record.name = name

	@api.depends( 'availability', 'minutes', 'breakdown', 'standby' )
	def _compute_performance(self):
		for record in self:
			if record.minutes + record.breakdown + record.standby != 0 :
				record.physical_availability = ( record.minutes + record.standby ) / (record.minutes + record.breakdown + record.standby) * 100
				record.effective_utilization = ( record.minutes ) / (record.minutes + record.breakdown + record.standby) * 100
			if record.minutes + record.standby != 0 :
				record.used_availability = ( record.minutes ) / (record.minutes + record.standby) * 100
			if record.minutes + record.breakdown != 0 :
				record.mechanical_availability = ( record.minutes ) / (record.minutes + record.breakdown) * 100
	
	@api.multi
	def action_done(self):
		for order in self:
			order.write({'state': 'done'})

	@api.multi
	def action_confirm(self):
		for order in self:
			order.write({ 'state' : 'confirm' })
				
	@api.multi
	def action_draft(self):
		for order in self:
			order.write({'state': 'draft'})

	@api.multi
	def action_reload(self):
		for record in self: 
			# record.log_ids.unlink()
			Ritase_log = self.env['production.ritase.log'].sudo()
			logs = Ritase_log.search([ ( 'vehicle_id', '=', self.vehicle_id.id ), ( 'datetime', '>=', record.date+" 00:00:01" ), ( 'datetime', '<=', record.end_date+" 23:00:59" ) ])
			record.update({
				'log_ids': [( 6, 0, logs.ids )],
			})

			Ritase_counter = self.env['production.ritase.counter'].sudo()
			counters = Ritase_counter.search([ ( 'vehicle_id', '=', self.vehicle_id.id ), ( 'date', '>=', record.date ), ( 'date', '<=', record.end_date ) ])
			record.update({
				'counter_ids': [( 6, 0, counters.ids )],
			})
			record.minutes = sum( [ x.minutes for x in counters ] )

			Losstimes = self.env['fleet.vehicle.losstime'].sudo()
			losstimes = Losstimes.search([ ( 'vehicle_id', '=', self.vehicle_id.id ), ( 'date', '>=', record.date ), ( 'date', '<=', record.end_date ) ])
			record.update({
				'vehicle_losstime_ids': [( 6, 0, losstimes.ids )],
			})
			record.breakdown = sum( [ x.minutes for x in losstimes if(x.losstime_type == "breakdown") ] )
			record.standby = sum( [ x.minutes for x in losstimes if(x.losstime_type != "breakdown") ] )


