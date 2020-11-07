# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models
from calendar import monthrange
_logger = logging.getLogger(__name__)

class ProductionRitaseReport(models.TransientModel):
    _name = 'production.ritase.report'

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date(string="End Date", required=True)
    type = fields.Selection([
        ( "detail" , 'Detail'),
        ( "summary" , 'Summary'),
        ], default="detail", string='Type', index=True, required=True )

    @api.multi
    def action_print(self):        
        final_dict = {}
        if self.type == 'detail' :
            ritase_counters = self.env['production.ritase.counter'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
            rows = []
            for ritase_counter in ritase_counters:
                temp = {}
                temp["doc_name"] = ritase_counter.ritase_order_id.name
                temp["name"] = ritase_counter.name
                temp["date"] = ritase_counter.date
                if ritase_counter.location_id :
                    temp["location_name"] = ritase_counter.location_id.name
                else:
                    temp["location_name"] = "-"
                if ritase_counter.ritase_order_id.location_dest_id :
                    temp["location_dest_name"] = ritase_counter.ritase_order_id.location_dest_id.name
                else:
                    temp["location_dest_name"] = "-"
                temp["vehicle_name"] = ritase_counter.vehicle_id.name
                temp["driver_name"] = ritase_counter.driver_id.name
                temp["ritase_count"] = ritase_counter.ritase_count
                temp["amount"] = ritase_counter.amount
                rows.append(temp)
            final_dict["rows"] = rows
        elif self.type == 'summary' :
            ritase_orders = self.env['production.ritase.order'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "done" ) ])
            loc_dest_ritase_dict = {}
            for ritase_order in ritase_orders:
                if loc_dest_ritase_dict.get( ritase_order.location_id.name , False):
                    if loc_dest_ritase_dict[ ritase_order.location_id.name ].get( ritase_order.location_dest_id.name , False):
                        loc_dest_ritase_dict[ ritase_order.location_id.name ][ ritase_order.location_dest_id.name ]["ritase_count"] += ritase_order.ritase_count
                    else :
                        loc_dest_ritase_dict[ ritase_order.location_id.name ][ ritase_order.location_dest_id.name ] =  {
                            "date" : ritase_order.date,
                            "doc_name" : ritase_order.name,
                            "location_name" : ritase_order.location_id.name,
                            "location_dest_name" : ritase_order.location_dest_id.name,
                            "ritase_count" : ritase_order.ritase_count,
                        } 
                else :
                    loc_dest_ritase_dict[ ritase_order.location_id.name ] = {}
                    loc_dest_ritase_dict[ ritase_order.location_id.name ][ ritase_order.location_dest_id.name ] =  {
                            "date" : ritase_order.date,
                            "doc_name" : ritase_order.name,
                            "location_name" : ritase_order.location_id.name,
                            "location_dest_name" : ritase_order.location_dest_id.name,
                            "ritase_count" : ritase_order.ritase_count,
                        } 
            # loc_ritase_dict = {}
            # for ritase_order in ritase_orders:
            #     if loc_ritase_dict.get( ritase_order.location_id.name , False):
            #         loc_ritase_dict[ ritase_order.location_id.name ]["ritase_count"] += ritase_order.ritase_count
            #     else :
            #         loc_ritase_dict[ ritase_order.location_id.name ] =  {
            #                 "date" : ritase_order.date,
            #                 "doc_name" : ritase_order.name,
            #                 "location_name" : ritase_order.location_id.name,
            #                 "location_dest_name" : ritase_order.location_dest_id.name,
            #                 "ritase_count" : ritase_order.ritase_count,
            #             } 
            
            final_dict = loc_dest_ritase_dict
        
        datas = {
            'ids': self.ids,
            'model': 'production.ritase.report',
            'form': final_dict,
            'type': self.type,
            'start_date': self.start_date,
            'end_date': self.end_date,

        }
        # _logger.warning( loc_dest_ritase_dict )
        return self.env['report'].get_action(self,'mining_production.production_ritase_temp', data=datas)
