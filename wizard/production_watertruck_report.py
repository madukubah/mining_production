# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models
from calendar import monthrange
_logger = logging.getLogger(__name__)

class ProductionWatertruckReport(models.TransientModel):
    _name = 'production.watertruck.report'

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date(string="End Date", required=True)
    type = fields.Selection([
        ( "detail" , 'Detail'),
        # ( "summary" , 'Summary'),
        ( "per_employee" , 'Per Employee'),
        ], default="detail", string='Type', index=True, required=True )

    @api.multi
    def action_print(self):        
        final_dict = {}
        if self.type == 'detail' :
            watertruck_counters = self.env['production.watertruck.counter'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
            rows = []
            for watertruck_counter in watertruck_counters:
                temp = {}
                temp["doc_name"] = watertruck_counter.order_id.name
                temp["name"] = watertruck_counter.name
                temp["date"] = watertruck_counter.date
                temp["vehicle_name"] = watertruck_counter.vehicle_id.name
                temp["driver_name"] = watertruck_counter.driver_id.name
                temp["ritase_count"] = watertruck_counter.ritase_count
                temp["amount"] = watertruck_counter.amount
                rows.append(temp)
            final_dict["rows"] = rows
        # elif self.type == 'summary' :
        #     ritase_orders = self.env['production.watertruck.order'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "done" ) ])
        #     loc_dest_ritase_dict = {}
        #     for ritase_order in ritase_orders:
        #         if loc_dest_ritase_dict.get( ritase_order.location_id.name , False):
        #             if loc_dest_ritase_dict[ ritase_order.location_id.name ].get( ritase_order.location_dest_id.name , False):
        #                 loc_dest_ritase_dict[ ritase_order.location_id.name ][ ritase_order.location_dest_id.name ]["ritase_count"] += ritase_order.ritase_count
        #             else :
        #                 loc_dest_ritase_dict[ ritase_order.location_id.name ][ ritase_order.location_dest_id.name ] =  {
        #                     "date" : ritase_order.date,
        #                     "doc_name" : ritase_order.name,
        #                     "location_name" : ritase_order.location_id.name,
        #                     "location_dest_name" : ritase_order.location_dest_id.name,
        #                     "ritase_count" : ritase_order.ritase_count,
        #                 } 
        #         else :
        #             loc_dest_ritase_dict[ ritase_order.location_id.name ] = {}
        #             loc_dest_ritase_dict[ ritase_order.location_id.name ][ ritase_order.location_dest_id.name ] =  {
        #                     "date" : ritase_order.date,
        #                     "doc_name" : ritase_order.name,
        #                     "location_name" : ritase_order.location_id.name,
        #                     "location_dest_name" : ritase_order.location_dest_id.name,
        #                     "ritase_count" : ritase_order.ritase_count,
        #                 } 
        #     final_dict = loc_dest_ritase_dict
        elif self.type == 'per_employee' :
            watertruck_counters = self.env['production.watertruck.counter'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
            employee_ritase_dict = {}
            for watertruck_counter in watertruck_counters:
                temp = {}
                temp["doc_name"] = watertruck_counter.order_id.name
                temp["name"] = watertruck_counter.name
                temp["date"] = watertruck_counter.date
                temp["vehicle_name"] = watertruck_counter.vehicle_id.name
                temp["driver_name"] = watertruck_counter.driver_id.name
                temp["ritase_count"] = watertruck_counter.ritase_count
                temp["amount"] = watertruck_counter.amount

                if employee_ritase_dict.get( watertruck_counter.driver_id.name , False):
                    employee_ritase_dict[ watertruck_counter.driver_id.name ] += [ temp ]
                else:
                    employee_ritase_dict[ watertruck_counter.driver_id.name ] = [ temp ]
                    
            final_dict = employee_ritase_dict
        datas = {
            'ids': self.ids,
            'model': 'production.watertruck.report',
            'form': final_dict,
            'type': self.type,
            'start_date': self.start_date,
            'end_date': self.end_date,
        }
        # _logger.warning( loc_dest_ritase_dict )
        return self.env['report'].get_action(self,'mining_production.production_watertruck_temp', data=datas)
