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
        ritase_counters = self.env['production.ritase.counter'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
        rows = []
        if self.type == 'detail' :
            for ritase_counter in ritase_counters:
                temp = {}
                temp["doc_name"] = ritase_counter.ritase_order_id.name
                temp["name"] = ritase_counter.name
                temp["date"] = ritase_counter.date
                temp["vehicle_name"] = ritase_counter.vehicle_id.name
                temp["driver_name"] = ritase_counter.driver_id.name
                temp["ritase_count"] = ritase_counter.ritase_count
                temp["amount"] = ritase_counter.amount
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
