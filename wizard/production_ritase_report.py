# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models
from calendar import monthrange
_logger = logging.getLogger(__name__)

class ProductionRitaseReport(models.TransientModel):
    _name = 'production.ritase.report'

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date(string="End Date", required=True)
    mode = fields.Selection([
        ( "detail" , 'Detail'),
        ( "recap" , 'Recap'),
        ], default="detail", string='Mode', index=True, required=True )

    @api.multi
    def action_print(self):
        dumptruck_activites = self.env['mining.dumptruck.activity'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
        rows = []
        if self.mode == 'detail' :
            for dumptruck_activity in dumptruck_activites:
                temp = {}
                temp["doc_name"] = dumptruck_activity.ritase_order_id.name
                temp["name"] = dumptruck_activity.name
                temp["date"] = dumptruck_activity.date
                temp["vehicle_name"] = dumptruck_activity.vehicle_id.name
                temp["driver_name"] = dumptruck_activity.driver_id.name
                temp["ritase_count"] = dumptruck_activity.ritase_count
                temp["amount"] = dumptruck_activity.cost_amount
                rows.append(temp)

        final_dict = {}
        final_dict["rows"] = rows
        
        datas = {
            'ids': self.ids,
            'model': 'production.ritase.report',
            'form': final_dict,
            'start_date': self.start_date,
            'end_date': self.end_date,

        }
        # _logger.warning( datas )
        return self.env['report'].get_action(self,'mining_production.production_ritase_temp', data=datas)
