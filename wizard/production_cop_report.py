# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

class ProductionCopReport(models.TransientModel):
    _name = 'production.cop.report'

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date(string="End Date", required=True)

    @api.multi
    def action_print(self):
        tag_logs = self.env['production.cop.tag.log'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
        rows = []
        for tag_log in tag_logs:
            temp = {}
            temp["name"] = tag_log.name
            temp["date"] = tag_log.date
            temp["tag_name"] = tag_log.tag_id.name
            temp["product_uom_qty"] = tag_log.product_uom_qty
            temp["price_unit"] = tag_log.price_unit
            temp["amount"] = tag_log.amount
            rows.append(temp)

        final_dict = {}
        final_dict["cop"] = rows
        # for user in groupby_dict.keys():
        #     temp = []
        #     for order in groupby_dict[user]:
        #         temp_2 = []
        #         temp_2.append(order.name)
        #         temp_2.append(order.date_order)
        #         temp_2.append(order.amount_total)
        #         temp_2.append(order.partner_id.display_name)
        #         temp.append(temp_2)
        #     final_dict[user] = temp
        datas = {
            'ids': self.ids,
            'model': 'production.cop.report',
            'form': final_dict,
            'start_date': self.start_date,
            'end_date': self.end_date,

        }
        _logger.warning( datas )
        return self.env['report'].get_action(self,'mining_production.production_cop_temp', data=datas)
