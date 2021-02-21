# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models
from calendar import monthrange
_logger = logging.getLogger(__name__)

class ProductionHourmeterReport(models.TransientModel):
    _name = 'production.hourmeter.report'

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date(string="End Date", required=True)
    type = fields.Selection([
        # ( "detail" , 'Detail'),
        # ( "summary" , 'Summary'),
        ( "per_employee" , 'Per Employee (Detailed)'),
        ( "per_employee_summary" , 'Summary Employee'),
        ], default="per_employee", string='Type', index=True, required=True )

    @api.multi
    def action_print(self):
        # hourmeter_logs = self.env['production.vehicle.hourmeter.log'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ], order="start_datetime asc")
        hourmeter_logs = self.env['production.vehicle.hourmeter.log'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ) ], order="date asc, start_datetime asc")
        rows = []
        for hourmeter_log in hourmeter_logs:
            temp = {}
            temp["doc_name"] = hourmeter_log.hourmeter_order_id.name
            temp["name"] = hourmeter_log.name
            temp["shift"] = hourmeter_log.shift
            temp["cost_code"] = hourmeter_log.cost_code_id.name if hourmeter_log.cost_code_id else " "
            temp["date"] = hourmeter_log.date
            temp["location_name"] = hourmeter_log.location_id.name
            temp["vehicle_name"] = hourmeter_log.vehicle_id.name

            driver_name = hourmeter_log.driver_id.name
            if driver_name.find("[") != -1:
                driver_name = driver_name[0: int( driver_name.find("[") ) ]
            temp["driver_name"] = driver_name

            temp["start_datetime"] = hourmeter_log.start_datetime
            temp["end_datetime"] = hourmeter_log.end_datetime
            temp["hours"] = hourmeter_log.hours

            temp["start"] = hourmeter_log.start
            temp["end"] = hourmeter_log.end
            temp["hourmeter_value"] = hourmeter_log.value

            temp["amount"] = hourmeter_log.amount
            rows.append(temp)

        final_dict = {}
        if self.type == 'detail' :
            final_dict["rows"] = rows
        elif self.type == 'summary' :
            vehicle_hourmeter_dict = {}
            for row in rows:
                if vehicle_hourmeter_dict.get( row["vehicle_name"] , False):
                    vehicle_hourmeter_dict[ row["vehicle_name"] ] += [ row ]
                else :
                    vehicle_hourmeter_dict[ row["vehicle_name"] ] = [ row ]
            final_dict = vehicle_hourmeter_dict
        elif self.type == 'per_employee' :
            employee_hourmeter_dict = {}
            for row in rows:
                if employee_hourmeter_dict.get( row["driver_name"] , False):
                    employee_hourmeter_dict[ row["driver_name"] ]["all"] += [ row ]
                else :
                    employee_hourmeter_dict[ row["driver_name"] ] = {}
                    employee_hourmeter_dict[ row["driver_name"] ]["col_1"] = []
                    employee_hourmeter_dict[ row["driver_name"] ]["col_2"] = []
                    employee_hourmeter_dict[ row["driver_name"] ]["shift_1"] = 0
                    employee_hourmeter_dict[ row["driver_name"] ]["shift_2"] = 0
                    employee_hourmeter_dict[ row["driver_name"] ]["all"] = [ row ]

            cols = ["col_1", "col_2"]
            for employee, hourmeter in employee_hourmeter_dict.items():
                for ind, hm in enumerate( hourmeter["all"] ):
                    hourmeter[ cols[ ind % 2 ] ] += [ hm ]
                    if hm["shift"] == "1" :
                        hourmeter["shift_1"] += hm["hourmeter_value"]
                    if hm["shift"] == "2" :
                        hourmeter["shift_2"] += hm["hourmeter_value"]

            final_dict = employee_hourmeter_dict
        elif self.type == 'per_employee_summary' :
            employee_hourmeter_dict = {}
            for row in rows:
                if employee_hourmeter_dict.get( row["driver_name"] , False):
                    employee_hourmeter_dict[ row["driver_name"] ]["all"] += [ row ]
                else :
                    employee_hourmeter_dict[ row["driver_name"] ] = {}
                    employee_hourmeter_dict[ row["driver_name"] ]["col_1"] = []
                    employee_hourmeter_dict[ row["driver_name"] ]["col_2"] = []
                    employee_hourmeter_dict[ row["driver_name"] ]["shift_1"] = 0
                    employee_hourmeter_dict[ row["driver_name"] ]["shift_2"] = 0
                    employee_hourmeter_dict[ row["driver_name"] ]["all"] = [ row ]

            cols = ["col_1", "col_2"]
            for employee, hourmeter in employee_hourmeter_dict.items():
                hourmeter["summary"] = {
                    "driver_name" : employee,
                    "shift_1" : 0,
                    "shift_2" : 0,
                    "total" : 0,
                }
                for ind, hm in enumerate( hourmeter["all"] ):
                    hourmeter[ cols[ ind % 2 ] ] += [ hm ]
                    if hm["shift"] == "1" :
                        hourmeter["shift_1"] += hm["hourmeter_value"]
                        hourmeter["summary"]["shift_1"] += hm["hourmeter_value"]
                    if hm["shift"] == "2" :
                        hourmeter["shift_2"] += hm["hourmeter_value"]
                        hourmeter["summary"]["shift_2"] += hm["hourmeter_value"]
                    hourmeter["summary"]["total"] += hm["hourmeter_value"]

            final_dict = employee_hourmeter_dict
        
        datas = {
            'ids': self.ids,
            'model': 'production.hourmeter.report',
            'form': final_dict,
            'type': self.type,
            'start_date': self.start_date,
            'end_date': self.end_date,

        }
        # _logger.warning( datas )
        return self.env['report'].get_action(self,'mining_production.production_hourmeter_temp', data=datas)
