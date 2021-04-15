# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime
from calendar import monthrange
import logging
_logger = logging.getLogger(__name__)

class ProductionCopReport(models.TransientModel):
    _name = 'production.cop.report'

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date(string="End Date", required=True)
    group_by_loc = fields.Boolean(
        'Group By Location', default=False )
    tag_ids = fields.Many2many('production.cop.tag', 'cop_report_tag_rel2', 'report_id', 'tag_id', 'Tag' )
    product_ids = fields.Many2many('product.product', 'cop_report_product_rel', 'report_id', 'product_id', 'Specific Items' )
    type = fields.Selection([
        ( "detail" , 'Detail'),
        ( "summary" , 'Summary'),
        ], default="detail", string='Type', index=True, required=True )

    @api.multi
    def action_print(self):
        tag_ids = self.tag_ids.ids
        service_types = self.env['fleet.service.type'].search([ ( 'tag_id', 'in', tag_ids ) ])
        stype_vehicle_cost_dict = {}
        stag_ids = []
        for service_type in service_types:
            stype_vehicle_cost_dict[ service_type.name ] = {
                "vehicles" : {},
                "total_amount" : 0
            }
            stag_ids += [ service_type.tag_id.id ]

        tag_ids = [ x for x in tag_ids if x not in stag_ids ]
        if self.product_ids.ids :
            vehicle_costs = self.env['fleet.vehicle.log.services'].search( [ ( "date", ">=", self.start_date ), ( "date", "<=", self.end_date ), ( "cost_subtype_id", "in", service_types.ids ), ( "product_id", "in", self.product_ids.ids )  ], order="date asc" )
        else :
            vehicle_costs = self.env['fleet.vehicle.log.services'].search( [ ( "date", ">=", self.start_date ), ( "date", "<=", self.end_date ), ( "cost_subtype_id", "in", service_types.ids ) ], order="date asc" )

        for vehicle_cost in vehicle_costs:
            stype = vehicle_cost.cost_subtype_id.name
            vehicle_name = vehicle_cost.vehicle_id.name
            driver_name = vehicle_cost.purchaser_id.name if vehicle_cost.purchaser_id else ""
            if driver_name.find("[") != -1:
                driver_name = driver_name[0: int( driver_name.find("[") ) ]
                
            if stype_vehicle_cost_dict[ stype ]["vehicles"].get( vehicle_name , False ):
               stype_vehicle_cost_dict[ stype ]["vehicles"][ vehicle_name ][ "list" ] += [
                   {
                        "date" : vehicle_cost.date,
                        "name" : vehicle_name,
                        "driver" : driver_name ,
                        "product" : vehicle_cost.product_id.name if vehicle_cost.product_id else "" ,
                        "product_uom_qty" : vehicle_cost.product_uom_qty,
                        "amount" : vehicle_cost.amount,
                    }
               ]
               stype_vehicle_cost_dict[ stype ]["vehicles"][ vehicle_name ][ "summary" ][ "product_uom_qty" ] += vehicle_cost.product_uom_qty
               stype_vehicle_cost_dict[ stype ]["vehicles"][ vehicle_name ][ "summary" ][ "amount" ] += vehicle_cost.amount

            else :
                stype_vehicle_cost_dict[ stype ]["vehicles"][ vehicle_name ] = {}
                stype_vehicle_cost_dict[ stype ]["vehicles"][ vehicle_name ][ "list" ] = [
                    {
                        "date" : vehicle_cost.date,
                        "name" : vehicle_name,
                        "driver" : driver_name ,
                        "product" : vehicle_cost.product_id.name if vehicle_cost.product_id else "" ,
                        "product_uom_qty" : vehicle_cost.product_uom_qty,
                        "amount" : vehicle_cost.amount,
                    }
                ]
                stype_vehicle_cost_dict[ stype ]["vehicles"][ vehicle_name ][ "summary" ] = {
                    "name" : vehicle_name,
                    "product_uom_qty" : vehicle_cost.product_uom_qty,
                    "amount" : vehicle_cost.amount,
                }

            stype_vehicle_cost_dict[ stype ]["total_amount"] += vehicle_cost.amount
            

        cop_tags = self.env['production.cop.tag'].search([ ( 'id', 'in', tag_ids ) ])
        tag_log_dict = {}
        for cop_tag in cop_tags:
            tag_log_dict[ cop_tag.name ] = {
                "items" : [],
                "total_amount" : 0
            }
        
        if self.product_ids.ids :
            tag_logs = self.env['production.cop.tag.log'].search( [ ( "date", ">=", self.start_date ), ( "date", "<=", self.end_date ), ( "tag_id", "in", tag_ids ), ( "product_id", "in", self.product_ids.ids )  ], order="date asc" )
        else:
            tag_logs = self.env['production.cop.tag.log'].search( [ ( "date", ">=", self.start_date ), ( "date", "<=", self.end_date ), ( "tag_id", "in", tag_ids )  ], order="date asc" )

        for tag_log in tag_logs:
            tag_name = tag_log.tag_id.name
            tag_log_dict[ tag_name ]["items"] += [
                {
                    "date" : tag_log.date,
                    "product" : tag_log.product_id.name if tag_log.product_id else "" ,
                    "product_uom_qty" : tag_log.product_uom_qty,
                    "amount" : tag_log.amount,
                    "remarks" : tag_log.remarks,
                }
            ]
            tag_log_dict[ tag_name ]["total_amount"] += tag_log.amount

        final_dict = {}
        final_dict["vehicle_cost"] = stype_vehicle_cost_dict
        final_dict["tag_log"] = tag_log_dict
        datas = {
            'ids': self.ids,
            'model': 'production.cop.report',
            'form': final_dict,
            'type': self.type,
            'start_date': self.start_date,
            'end_date': self.end_date,

        }
        return self.env['report'].get_action(self,'mining_production.production_cop_temp', data=datas)

    @api.multi
    def action_print2(self):
        tag_logs = self.env['production.cop.tag.log'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
        date_tag_log_dict = {}
        for tag_log in tag_logs:
            temp = {}
            temp["name"] = tag_log.name
            temp["date"] = tag_log.date
            temp["tag_name"] = tag_log.tag_id.name
            if tag_log.location_id :
                temp["location_name"] = tag_log.location_id.name
            else:
                temp["location_name"] = "Other"
            temp["product_uom_qty"] = tag_log.product_uom_qty
            temp["price_unit"] = tag_log.price_unit
            temp["amount"] = tag_log.amount
            if date_tag_log_dict.get( temp["date"] , False):
                if date_tag_log_dict[ temp["date"] ].get( temp["tag_name"] , False):
                    if date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ].get( temp["location_name"] , False):
                        date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ][ temp["location_name"] ][ "product_uom_qty" ] += temp[ "product_uom_qty" ]
                        # date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ][ temp["location_name"] ][ "price_unit" ] += temp[ "price_unit" ]
                        date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ][ temp["location_name"] ][ "amount" ] += temp[ "amount" ]
                    else:
                        date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ][ temp["location_name"] ] = temp    
                else:
                    date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ] = {}
                    date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ][ temp["location_name"] ] = temp
            else:
                date_tag_log_dict[ temp["date"] ] = {}
                date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ] = {}
                date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ][ temp["location_name"] ] = temp

        hr_contracts = self.env['hr.contract'].sudo().search([ "&", ( 'state', '=', "draft" ), ( 'department_id', '!=', "[(3,7,6,4,8,16)]" ) ])

        if hr_contracts:
            temp = {}
            temp["name"] = "Employee Salary"
            temp["date"] = self.start_date
            temp["tag_name"] = "Employee Salary"
            temp["location_name"] = "Other"
            temp["product_uom_qty"] = len( hr_contracts )
            sum_wage = sum( [hr_contract.wage  for hr_contract in hr_contracts if hr_contract.department_id.id not in (3,7,6,4,8) ] )
            start_date = datetime.strptime(self.start_date, '%Y-%m-%d')
            end_date = datetime.strptime(self.end_date, '%Y-%m-%d')
            day_length = ( end_date - start_date )
            days_in_month = monthrange( start_date.year , start_date.month )
            temp["price_unit"] = sum_wage  / days_in_month[1]
            temp["amount"] = round( temp["price_unit"] * abs( day_length.days + 1 ) , 2) 
            if date_tag_log_dict.get( temp["date"] , False):
                date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ]= {}
                date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ][ temp["location_name"] ] = temp
            else :
                date_tag_log_dict[ temp["date"] ] = {}
                date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ] = {}
                date_tag_log_dict[ temp["date"] ][ temp["tag_name"] ][ temp["location_name"] ] = temp
            # rows.append(temp)

        # ore production
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ], limit=1) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )

        production_orders = self.env['production.order'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "done" ), ( 'product_id', '=', production_config.lot_id.product_id.id ) ])
        production_rows = []
        for production_order in production_orders:
            temp = {}
            temp["name"] = production_order.name
            temp["date"] = production_order.date
            if production_order.location_id :
                temp["location_name"] = production_order.location_id.name
            else:
                temp["location_name"] = "Other"
            product = production_order.product_id
            product_uom_qty = production_order.product_uom_id._compute_quantity( production_order.product_qty, product.uom_id )
            temp["product_name"] = production_order.product_id.name
            temp["product_uom"] = production_order.product_uom_id.name
            temp["product_uom_qty"] = product_uom_qty
            temp["price_unit"] = production_order.product_id.standard_price
            temp["amount"] = production_order.product_id.standard_price * product_uom_qty
            production_rows.append(temp)

        final_dict = {}
        if self.group_by_loc :
            loc_cop_dict = {}
            for date, i in date_tag_log_dict.items():
                for tag, j in i.items():
                    for loc, k in j.items():
                        if loc_cop_dict.get( loc , False):
                            loc_cop_dict[ loc ] += [ k ]
                        else :
                            loc_cop_dict[ loc ]= [ k ]

            loc_production_dict = {}
            for row in production_rows:
                if loc_production_dict.get( row["location_name"] , False):
                    loc_production_dict[ row["location_name"] ] += [ row ]
                else :
                    loc_production_dict[ row["location_name"] ] = [ row ]

            final_dict["cop"] = loc_cop_dict
            final_dict["production"] = loc_production_dict
        else :
            final_dict["cop"] = date_tag_log_dict
            final_dict["production"] = production_rows
        
        datas = {
            'ids': self.ids,
            'model': 'production.cop.report',
            'form': final_dict,
            'group_by_loc': self.group_by_loc,
            'start_date': self.start_date,
            'end_date': self.end_date,

        }
        return self.env['report'].get_action(self,'mining_production.production_cop_temp', data=datas)

    # @api.multi
    # def action_print(self):
    #     tag_logs = self.env['production.cop.tag.log'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "posted" ) ])
    #     rows = []
    #     for tag_log in tag_logs:
    #         temp = {}
    #         temp["name"] = tag_log.name
    #         temp["date"] = tag_log.date
    #         temp["tag_name"] = tag_log.tag_id.name
    #         if tag_log.location_id :
    #             temp["location_name"] = tag_log.location_id.name
    #         else:
    #             temp["location_name"] = "-"
    #         temp["product_uom_qty"] = tag_log.product_uom_qty
    #         temp["price_unit"] = tag_log.price_unit
    #         temp["amount"] = tag_log.amount
    #         rows.append(temp)

    #     hr_contracts = self.env['hr.contract'].search([ "&", ( 'state', '=', "draft" ), ( 'department_id', '!=', "[(3,7,6,4,8,16)]" ) ])

    #     if hr_contracts:
    #         temp = {}
    #         temp["name"] = "Employee Salary"
    #         temp["date"] = self.start_date
    #         temp["tag_name"] = "Employee Salary"
    #         temp["location_name"] = "-"
    #         temp["product_uom_qty"] = len( hr_contracts )
    #         sum_wage = sum( [hr_contract.wage  for hr_contract in hr_contracts if hr_contract.department_id.id not in (3,7,6,4,8) ] )
    #         start_date = datetime.strptime(self.start_date, '%Y-%m-%d')
    #         end_date = datetime.strptime(self.end_date, '%Y-%m-%d')
    #         day_length = ( end_date - start_date )
    #         days_in_month = monthrange( start_date.year , start_date.month )
    #         temp["price_unit"] = sum_wage  / days_in_month[1]
    #         temp["amount"] = round( temp["price_unit"] * abs( day_length.days + 1 ) , 2) 
    #         rows.append(temp)

    #     # ore production
    #     ProductionConfig = self.env['production.config'].sudo()
    #     production_config = ProductionConfig.search([ ( "active", "=", True ) ], limit=1) 
    #     if not production_config :
    #         raise UserError(_('Please Set Configuration file') )

    #     production_orders = self.env['production.order'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "done" ), ( 'product_id', '=', production_config.lot_id.product_id.id ) ])
    #     production_rows = []
    #     for production_order in production_orders:
    #         temp = {}
    #         temp["name"] = production_order.name
    #         temp["date"] = production_order.date
    #         if production_order.location_id :
    #             temp["location_name"] = production_order.location_id.name
    #         else:
    #             temp["location_name"] = "Other"
    #         product = production_order.product_id
    #         product_uom_qty = production_order.product_uom_id._compute_quantity( production_order.product_qty, product.uom_id )
    #         temp["product_name"] = production_order.product_id.name
    #         temp["product_uom"] = production_order.product_uom_id.name
    #         temp["product_uom_qty"] = product_uom_qty
    #         temp["price_unit"] = production_order.product_id.standard_price
    #         temp["amount"] = production_order.product_id.standard_price * product_uom_qty
    #         production_rows.append(temp)

    #     final_dict = {}
    #     if self.group_by_loc :
    #         loc_cop_dict = {}
    #         for row in rows:
    #             if loc_cop_dict.get( row["location_name"] , False):
    #                 loc_cop_dict[ row["location_name"] ] += [ row ]
    #             else :
    #                 loc_cop_dict[ row["location_name"] ] = [ row ]
                    
    #         loc_production_dict = {}
    #         for row in production_rows:
    #             if loc_production_dict.get( row["location_name"] , False):
    #                 loc_production_dict[ row["location_name"] ] += [ row ]
    #             else :
    #                 loc_production_dict[ row["location_name"] ] = [ row ]

    #         final_dict["cop"] = loc_cop_dict
    #         final_dict["production"] = loc_production_dict
    #     else :
    #         final_dict["cop"] = rows
    #         final_dict["production"] = production_rows
        
    #     datas = {
    #         'ids': self.ids,
    #         'model': 'production.cop.report',
    #         'form': final_dict,
    #         'group_by_loc': self.group_by_loc,
    #         'start_date': self.start_date,
    #         'end_date': self.end_date,

    #     }
    #     return self.env['report'].get_action(self,'mining_production.production_cop_temp', data=datas)
