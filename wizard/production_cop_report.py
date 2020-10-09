# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models
from datetime import datetime
from calendar import monthrange
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

        hr_contracts = self.env['hr.contract'].search([ "&", ( 'state', '=', "draft" ), ( 'department_id', '!=', "[(3,7,6,4,8,16)]" ) ])

        if hr_contracts:
            temp = {}
            temp["name"] = "Employee Salary"
            temp["date"] = self.start_date
            temp["tag_name"] = "Employee Salary"
            temp["product_uom_qty"] = len( hr_contracts )
            sum_wage = sum( [hr_contract.wage  for hr_contract in hr_contracts if hr_contract.department_id.id not in (3,7,6,4,8) ] )
            start_date = datetime.strptime(self.start_date, '%Y-%m-%d')
            end_date = datetime.strptime(self.end_date, '%Y-%m-%d')
            day_length = ( end_date - start_date )
            days_in_month = monthrange( start_date.year , start_date.month )
            temp["price_unit"] = sum_wage  / days_in_month[1]
            temp["amount"] = round( temp["price_unit"] * abs( day_length.days + 1 ) , 2) 
            rows.append(temp)

        production_orders = self.env['production.order'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "done" ) ])
        production_rows = []
        for production_order in production_orders:
            temp = {}
            temp["name"] = production_order.name
            temp["date"] = production_order.date
            product = production_order.product_id
            product_uom_qty = production_order.product_uom_id._compute_quantity( production_order.product_qty, product.uom_id )
            temp["product_name"] = production_order.product_id.name
            temp["product_uom"] = production_order.product_uom_id.name
            temp["product_uom_qty"] = product_uom_qty
            temp["price_unit"] = production_order.product_id.standard_price
            temp["amount"] = production_order.product_id.standard_price * product_uom_qty
            production_rows.append(temp)

        final_dict = {}
        final_dict["cop"] = rows
        final_dict["production"] = production_rows
        
        datas = {
            'ids': self.ids,
            'model': 'production.cop.report',
            'form': final_dict,
            'start_date': self.start_date,
            'end_date': self.end_date,

        }
        # _logger.warning( datas )
        return self.env['report'].get_action(self,'mining_production.production_cop_temp', data=datas)
