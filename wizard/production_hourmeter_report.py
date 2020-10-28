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
        ( "detail" , 'Detail'),
        ( "summary" , 'Summary'),
        ], default="detail", string='Type', index=True, required=True )

    @api.multi
    def action_print(self):
        hourmeter_logs = self.env['production.vehicle.hourmeter.log'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
        rows = []
        if self.type == 'detail' :
            for hourmeter_log in hourmeter_logs:
                temp = {}
                temp["doc_name"] = hourmeter_log.hourmeter_order_id.name
                temp["name"] = hourmeter_log.name
                temp["date"] = hourmeter_log.date
                temp["vehicle_name"] = hourmeter_log.vehicle_id.name
                temp["driver_name"] = hourmeter_log.driver_id.name
                temp["hourmeter_value"] = hourmeter_log.value
                temp["amount"] = hourmeter_log.amount
                rows.append(temp)

        final_dict = {}
        final_dict["rows"] = rows
        
        datas = {
            'ids': self.ids,
            'model': 'production.hourmeter.report',
            'form': final_dict,
            'start_date': self.start_date,
            'end_date': self.end_date,

        }
        _logger.warning( datas )
        return self.env['report'].get_action(self,'mining_production.production_hourmeter_temp', data=datas)
