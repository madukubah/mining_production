# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from calendar import monthrange
import datetime
from dateutil.relativedelta import relativedelta
_logger = logging.getLogger(__name__)

class ProductionDTTimesheetReport(models.TransientModel):
    _name = 'production.dt.timesheet.report'

    @api.model
    def _default_config(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0]

    @api.model
    def _default_tag(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0].rit_vehicle_tag_id

    production_config_id = fields.Many2one('production.config', string='Production Config', default=_default_config )

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date(string="End Date", required=True)
    tag_id = fields.Many2one('fleet.vehicle.tag', string='Tag', default=_default_tag )
    vehicle_state_id = fields.Many2one('fleet.vehicle.state', string='Vehicle State' )
    is_all = fields.Boolean(string="All Vehicle", Default=False )
    vehicle_ids = fields.Many2many('fleet.vehicle', 'dt_timesheet_report_vehicle_rel', 'report_id', 'vehicle_id', string='Vehicles' )

    @api.onchange('is_all')
    def action_reload(self):
        for record in self: 
            if record.is_all :
                Vehicle = self.env['fleet.vehicle'].sudo()
                vehicles = Vehicle.search( [ ( "tag_ids", "in", record.tag_id.id ), ( "state_id", "=", record.vehicle_state_id.id ) ] )
                record.vehicle_ids = vehicles
            else :
                record.vehicle_ids = []

    @api.multi
    def action_print(self):
        start = datetime.datetime.strptime( self.start_date, '%Y-%m-%d')
        start -= datetime.timedelta(days=1)
        _start_date = start.strftime( '%Y-%m-%d')
        end = datetime.datetime.strptime( self.end_date, '%Y-%m-%d')
        diff = relativedelta(end, start)
        days_in_month = monthrange( end.year , end.month )
        days = abs( diff.days + diff.months * days_in_month[1] )

        vehicle_date_dict = {}
        dates = []
        for vehicle in self.vehicle_ids: 
            dates = []
            vehicle_date_dict[ vehicle.name ] = {}
            start = datetime.datetime.strptime( self.start_date, '%Y-%m-%d')
            start -= datetime.timedelta(days=1)
            date = start.strftime( '%Y-%m-%d')
            for i in range( days+1 ) :
                dates += [ date ]
                vehicle_date_dict[ vehicle.name ][ date ] = {
                    "date" : date,
                    "odometer_start" : 0,
                    "odometer_end" : 0,
                    "value" : 0,
                    "remarks" : "",
                    "fuel_consumption" : 0,
                }
                start += datetime.timedelta(days=1)
                date = start.strftime( '%Y-%m-%d')
            
            vehicle_date_dict[ vehicle.name ]["dates"] = dates

        vehicle_odometers = self.env['fleet.vehicle.odometer'].sudo().search([ ( 'date', '>=', _start_date ), ( 'date', '<=', self.end_date ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ) ], order="vehicle_id asc, date asc")
        for vehicle_odometer in vehicle_odometers: 
            vehicle_name = vehicle_odometer.vehicle_id.name
            if vehicle_date_dict.get( vehicle_name , False):
                date = vehicle_odometer.date
                if vehicle_date_dict[ vehicle_name ].get( date , False):
                    vehicle_date_dict[ vehicle_name ][ date ][ "odometer_end" ] = max( vehicle_odometer.value, vehicle_date_dict[ vehicle_name ][ date ][ "odometer_end" ] )

        vehicle_losstimes = self.env['fleet.vehicle.losstime'].sudo().search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ) ], order="vehicle_id asc, start_datetime asc")
        for vehicle_losstime in vehicle_losstimes: 
            vehicle_name = vehicle_losstime.vehicle_id.name
            if vehicle_date_dict.get( vehicle_name , False):
                date = vehicle_losstime.date
                if vehicle_date_dict[ vehicle_name ].get( date , False):
                    vehicle_date_dict[ vehicle_name ][ date ][ "remarks" ] += str( vehicle_losstime.remarks ) + ", "
        
        # fuels
        # vehicle_log_fuels = self.env['fleet.vehicle.log.fuel'].sudo().search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ) ], order="vehicle_id asc, date asc")
        # for vehicle_log_fuel in vehicle_log_fuels: 
        #     vehicle_name = vehicle_log_fuel.vehicle_id.name
        #     if vehicle_date_dict.get( vehicle_name , False):
        #         date = vehicle_log_fuel.date
        #         if vehicle_date_dict[ vehicle_name ].get( date , False):
        #             vehicle_date_dict[ vehicle_name ][ date ][ "fuel_consumption" ] += vehicle_log_fuel.liter
        _fuel_product_ids = set( [ x.product_id.id for x in self.production_config_id.refuel_service_type_ids  ] ) 
        _fuel_product_ids = list(_fuel_product_ids) 
        vehicle_costs = self.env['fleet.vehicle.cost'].sudo().search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ), ( 'product_id', 'in', _fuel_product_ids ) ], order="vehicle_id asc, date asc")
        for vehicle_cost in vehicle_costs: 
            vehicle_name = vehicle_cost.vehicle_id.name
            if vehicle_date_dict.get( vehicle_name , False):
                date = vehicle_cost.date
                if vehicle_date_dict[ vehicle_name ].get( date , False):
                    vehicle_date_dict[ vehicle_name ][ date ][ "fuel_consumption" ] += vehicle_cost.product_uom_qty

        for vehicle in self.vehicle_ids: 
            vehicle_name = vehicle.name
            dates = vehicle_date_dict[ vehicle_name ][ "dates" ]
            for i in range( days+1 ) :
                if i == 0 : continue
                vehicle_date_dict[ vehicle_name ][ dates[i] ][ "odometer_start" ] = vehicle_date_dict[ vehicle_name ][ dates[i-1] ][ "odometer_end" ]
                if vehicle_date_dict[ vehicle_name ][ dates[i] ][ "odometer_end" ] != 0 :
                    vehicle_date_dict[ vehicle_name ][ dates[i] ][ "value" ] = vehicle_date_dict[ vehicle_name ][ dates[i] ][ "odometer_end" ] - vehicle_date_dict[ vehicle_name ][ dates[i] ][ "odometer_start" ]
            del vehicle_date_dict[ vehicle_name ][ "dates" ][0]
            vehicle_date_dict[ vehicle_name ]["start"] = 0
            vehicle_date_dict[ vehicle_name ]["end"] = 0
            for date in vehicle_date_dict[ vehicle_name ][ "dates" ]: 
                if vehicle_date_dict[ vehicle_name ][ date ][ "odometer_start" ] !=0 :
                    vehicle_date_dict[ vehicle_name ]["start"] = vehicle_date_dict[ vehicle_name ][ date ][ "odometer_start" ]
                    break
            for date in reversed( vehicle_date_dict[ vehicle_name ][ "dates" ] ): 
                if vehicle_date_dict[ vehicle_name ][ date ][ "odometer_end" ] !=0 :
                    vehicle_date_dict[ vehicle_name ]["end"] = vehicle_date_dict[ vehicle_name ][ date ][ "odometer_end" ]
                    break

            
        datas = {
            'ids': self.ids,
            'model': 'production.he.hourmeter.report',
            'form': vehicle_date_dict,
            'start_date': self.start_date,
            'end_date': self.end_date,
        }
        # _logger.warning( vehicle_date_dict )
        return self.env['report'].with_context( landscape=True ).get_action(self,'mining_production.production_dt_timesheet_temp', data=datas)

    