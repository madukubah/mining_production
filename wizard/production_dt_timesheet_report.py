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
    def _default_tag(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0].rit_vehicle_tag_id

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
        
        vehicle_log_fuels = self.env['fleet.vehicle.log.fuel'].sudo().search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ) ], order="vehicle_id asc, date asc")
        for vehicle_log_fuel in vehicle_log_fuels: 
            vehicle_name = vehicle_log_fuel.vehicle_id.name
            if vehicle_date_dict.get( vehicle_name , False):
                date = vehicle_log_fuel.date
                if vehicle_date_dict[ vehicle_name ].get( date , False):
                    vehicle_date_dict[ vehicle_name ][ date ][ "fuel_consumption" ] += vehicle_log_fuel.liter

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

    @api.multi
    def action_print_2(self):
        start = datetime.datetime.strptime( self.start_date, '%Y-%m-%d')
        end = datetime.datetime.strptime( self.end_date, '%Y-%m-%d')
        days = abs( relativedelta(end, start).days )

        vehicle_date_dict = {}
        dates = []
        for vehicle in self.vehicle_ids: 
            dates = []
            vehicle_date_dict[ vehicle.name ] = {}
            start = datetime.datetime.strptime( self.start_date, '%Y-%m-%d')
            date = self.start_date
            for i in range( days+1 ) :
                dates += [ date ]
                # _logger.warning( date )
                vehicle_date_dict[ vehicle.name ][ date ] = {
                    "date" : date,
                    "shift_1_start" : 0,
                    "shift_1_end" : 0,
                    "shift_1_value" : 0,
                    "shift_1_operator" : "",
                    "breakdown" : 0,
                    "no_instruction" : 0,
                    "rainy" : 0,
                    "slippery" : 0,
                    "no_operator" : 0,
                    "total_standby" : 0,
                    "remark_losstime" : "",
                    "shift_2_start" : 0,
                    "shift_2_end" : 0,
                    "shift_2_value" : 0,
                    "shift_2_operator" : "",
                    "shift_2_remarks" : "",
                    "hm_total" : 0,
                    "fuel_consumption" : 0,
                }
                start += datetime.timedelta(days=1)
                date = start.strftime( '%Y-%m-%d')
            
            vehicle_date_dict[ vehicle.name ]["dates"] = dates

        # _logger.warning( vehicle_date_dict )
        hourmeter_logs = self.env['production.vehicle.hourmeter.log'].sudo().search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ) ], order="vehicle_id asc, start_datetime asc")
        for hourmeter_log in hourmeter_logs: 
            vehicle_name = hourmeter_log.vehicle_id.name
            # _logger.warning( vehicle_name )
            if vehicle_date_dict.get( vehicle_name , False):
                # _logger.warning( "vehicle_name" )
                date = hourmeter_log.date
                # _logger.warning( date )
                # _logger.warning( vehicle_date_dict[ vehicle_name ][date] )
                if vehicle_date_dict[ vehicle_name ].get( date , False):
                    if hourmeter_log.shift == "1" :
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_start" ] += hourmeter_log.start
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_end" ] += hourmeter_log.end
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_value" ] += hourmeter_log.value
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_operator" ] = hourmeter_log.driver_id.name
                    else :
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_start" ] += hourmeter_log.start
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_end" ] += hourmeter_log.end
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_value" ] += hourmeter_log.value
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_operator" ] = hourmeter_log.driver_id.name
                    # _logger.warning( "vehicle_name" )
                    vehicle_date_dict[ vehicle_name ][ date ][ "hm_total" ] += hourmeter_log.value

        vehicle_losstimes = self.env['fleet.vehicle.losstime'].sudo().search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ) ], order="vehicle_id asc, start_datetime asc")
        for vehicle_losstime in vehicle_losstimes: 
            vehicle_name = vehicle_losstime.vehicle_id.name
            if vehicle_date_dict.get( vehicle_name , False):
                date = vehicle_losstime.date
                if vehicle_date_dict[ vehicle_name ].get( date , False):
                    if vehicle_losstime.losstime_type == "breakdown" :
                        vehicle_date_dict[ vehicle_name ][ date ][ "breakdown" ] += vehicle_losstime.hours
                    if vehicle_losstime.losstime_type == "slippery" :
                        vehicle_date_dict[ vehicle_name ][ date ][ "slippery" ] += vehicle_losstime.hours
                    if vehicle_losstime.losstime_type == "rainy" :
                        vehicle_date_dict[ vehicle_name ][ date ][ "rainy" ] += vehicle_losstime.hours
                    if vehicle_losstime.losstime_type == "no_operator" :
                        vehicle_date_dict[ vehicle_name ][ date ][ "no_operator" ] += vehicle_losstime.hours
                    vehicle_date_dict[ vehicle_name ][ date ][ "total_standby" ] += vehicle_losstime.hours
                    vehicle_date_dict[ vehicle_name ][ date ][ "remark_losstime" ] += str( vehicle_losstime.remarks ) + ", "
        
        vehicle_log_fuels = self.env['fleet.vehicle.log.fuel'].sudo().search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ) ], order="vehicle_id asc, date asc")
        for vehicle_log_fuel in vehicle_log_fuels: 
            vehicle_name = vehicle_log_fuel.vehicle_id.name
            if vehicle_date_dict.get( vehicle_name , False):
                date = vehicle_log_fuel.date
                if vehicle_date_dict[ vehicle_name ].get( date , False):
                    vehicle_date_dict[ vehicle_name ][ date ][ "fuel_consumption" ] += vehicle_log_fuel.liter

        for vehicle in self.vehicle_ids: 
            vehicle_name = vehicle.name
            vehicle_date_dict[ vehicle_name ]["start"] = 0
            vehicle_date_dict[ vehicle_name ]["end"] = 0
            vehicle_date_dict[ vehicle_name ]["shift_1_start"] = 0
            vehicle_date_dict[ vehicle_name ]["shift_2_start"] = 0
            for date in vehicle_date_dict[ vehicle_name ][ "dates" ]: 
                if vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_start" ] !=0 :
                    vehicle_date_dict[ vehicle_name ]["shift_1_start"] = vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_start" ]
                if vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_start" ] !=0 :
                    vehicle_date_dict[ vehicle_name ]["shift_2_start"] = vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_start" ]
                if vehicle_date_dict[ vehicle_name ]["shift_1_start"] or vehicle_date_dict[ vehicle_name ]["shift_2_start"] :
                    vehicle_date_dict[ vehicle_name ]["start"] = min( vehicle_date_dict[ vehicle_name ]["shift_1_start"] , vehicle_date_dict[ vehicle_name ]["shift_2_start"] )
                    break
                vehicle_date_dict[ vehicle_name ]["start"] = min( vehicle_date_dict[ vehicle_name ]["shift_1_start"] , vehicle_date_dict[ vehicle_name ]["shift_2_start"] )

            vehicle_date_dict[ vehicle_name ]["shift_1_end"] = 0
            vehicle_date_dict[ vehicle_name ]["shift_2_end"] = 0  
            for date in reversed( vehicle_date_dict[ vehicle_name ][ "dates" ] ): 
                if vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_end" ] !=0 :
                    vehicle_date_dict[ vehicle_name ]["shift_2_end"] = vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_end" ]
                if vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_end" ] !=0 :
                    vehicle_date_dict[ vehicle_name ]["shift_2_end"] = vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_end" ]
                if vehicle_date_dict[ vehicle_name ]["shift_1_end"] or vehicle_date_dict[ vehicle_name ]["shift_2_end"] :
                    vehicle_date_dict[ vehicle_name ]["end"] = max( vehicle_date_dict[ vehicle_name ]["shift_1_end"] , vehicle_date_dict[ vehicle_name ]["shift_2_end"] )
                    break
                vehicle_date_dict[ vehicle_name ]["end"] = max( vehicle_date_dict[ vehicle_name ]["shift_1_end"] , vehicle_date_dict[ vehicle_name ]["shift_2_end"] )



        datas = {
            'ids': self.ids,
            'model': 'production.he.hourmeter.report',
            'form': vehicle_date_dict,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'dates': dates,
        }
        # _logger.warning( vehicle_date_dict )
        return self.env['report'].with_context( landscape=True ).get_action(self,'mining_production.production_he_hourmeter_temp', data=datas)
