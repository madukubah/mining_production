# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

import datetime
from dateutil.relativedelta import relativedelta
_logger = logging.getLogger(__name__)

class ProductionHEHourmeterReport(models.TransientModel):
    _name = 'production.he.hourmeter.report'

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
        return production_config[0].hm_vehicle_tag_id

    production_config_id = fields.Many2one('production.config', string='Production Config', default=_default_config )

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date(string="End Date", required=True)
    tag_id = fields.Many2one('fleet.vehicle.tag', string='Tag', default=_default_tag )
    vehicle_state_id = fields.Many2one('fleet.vehicle.state', string='Vehicle State' )
    is_all = fields.Boolean(string="All Vehicle", Default=False )
    vehicle_ids = fields.Many2many('fleet.vehicle', 'he_hourmeter_report_vehicle_rel', 'report_id', 'vehicle_id', string='Vehicles' )

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

        # hourmeter_logs
        hourmeter_logs = self.env['production.vehicle.hourmeter.log'].sudo().search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'vehicle_id', 'in', self.vehicle_ids.ids ) ], order="vehicle_id asc, start_datetime asc")
        for hourmeter_log in hourmeter_logs: 
            vehicle_name = hourmeter_log.vehicle_id.name
            if vehicle_date_dict.get( vehicle_name , False):
                date = hourmeter_log.date
                if vehicle_date_dict[ vehicle_name ].get( date , False):
                    if hourmeter_log.shift == "1" :
                        start = vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_start" ]
                        end = vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_end" ]
                        operator = vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_operator" ]

                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_start" ] = min( start, hourmeter_log.start) if start !=0 else hourmeter_log.start
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_end" ] = max( end, hourmeter_log.end)
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_value" ] += hourmeter_log.value
                        if hourmeter_log.driver_id.name not in operator :
                            vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_operator" ] += str( hourmeter_log.driver_id.name ) + ", "
                        else:
                            vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_operator" ] = str( hourmeter_log.driver_id.name )
                    else :
                        start = vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_start" ]
                        end = vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_end" ]
                        operator = vehicle_date_dict[ vehicle_name ][ date ][ "shift_1_operator" ]

                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_start" ] = min( start, hourmeter_log.start) if start !=0 else hourmeter_log.start
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_end" ] = max( end, hourmeter_log.end)
                        vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_value" ] += hourmeter_log.value
                        if hourmeter_log.driver_id.name not in operator :
                            vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_operator" ] += str( hourmeter_log.driver_id.name ) + ", "
                        else:
                            vehicle_date_dict[ vehicle_name ][ date ][ "shift_2_operator" ] = str( hourmeter_log.driver_id.name )
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
                    if vehicle_date_dict[ vehicle_name ]["shift_1_start"] == 0:
                        vehicle_date_dict[ vehicle_name ]["start"] = vehicle_date_dict[ vehicle_name ]["shift_2_start"]
                        break
                    if vehicle_date_dict[ vehicle_name ]["shift_2_start"] == 0:
                        vehicle_date_dict[ vehicle_name ]["start"] = vehicle_date_dict[ vehicle_name ]["shift_1_start"]
                        break
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
