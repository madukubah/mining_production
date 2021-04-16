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
            vehicle_costs = self.env['fleet.vehicle.cost'].search( [ ( "date", ">=", self.start_date ), ( "date", "<=", self.end_date ), ( "cost_subtype_id", "in", service_types.ids ), ( "state", "=", "posted" ), ( "product_id", "in", self.product_ids.ids )  ], order="date asc" )
        else :
            vehicle_costs = self.env['fleet.vehicle.cost'].search( [ ( "date", ">=", self.start_date ), ( "date", "<=", self.end_date ), ( "cost_subtype_id", "in", service_types.ids ), ( "state", "=", "posted" ) ], order="date asc" )

        for vehicle_cost in vehicle_costs:
            stype = vehicle_cost.cost_subtype_id.name
            vehicle_name = vehicle_cost.vehicle_id.name
            driver_name = ""
            services = self.env['fleet.vehicle.log.services'].search([ ( "cost_id", "=", vehicle_cost.id ) ], limit = 1)
            if services :
                driver_name = services[0].purchaser_id.name if services[0].purchaser_id else ""
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
            tag_logs = self.env['production.cop.tag.log'].search( [ ( "date", ">=", self.start_date ), ( "date", "<=", self.end_date ), ( "tag_id", "in", tag_ids ), ( "state", "=", "posted" ), ( "product_id", "in", self.product_ids.ids )  ], order="date asc" )
        else:
            tag_logs = self.env['production.cop.tag.log'].search( [ ( "date", ">=", self.start_date ), ( "date", "<=", self.end_date ), ( "tag_id", "in", tag_ids ), ( "state", "=", "posted" )  ], order="date asc" )

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