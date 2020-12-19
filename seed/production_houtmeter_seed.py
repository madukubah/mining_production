# -*- coding: utf-8 -*-

import logging
import random
import time
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from calendar import monthrange
_logger = logging.getLogger(__name__)

class ProductionHoutmeterSeed(models.TransientModel):
    _name = 'production.houtmeter.seed'

    @api.model
    def _default_employee(self):
        data = self.env['hr.employee'].sudo().search([ ], limit =1) 
        return data[0]
    
    @api.model
    def _default_load_vehicle_id(self):
        data = self.env['fleet.vehicle'].sudo().search([ ], limit =1) 
        return data[0]
    
    @api.model
    def _default_pile_vehicle_id(self):
        data = self.env['fleet.vehicle'].sudo().search([ ], limit =1) 
        return data[0]
    
    @api.model
    def _default_cost_code_id(self):
        data = self.env['production.cost.code'].sudo().search([ ], limit =1) 
        return data[0]
    
    @api.model
    def _default_block_id(self):
        data = self.env['production.block'].sudo().search([ ], limit =1) 
        return data[0]

    @api.model
    def _default_picking_type(self):
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get('company_id') or self.env.user.company_id.id
        types = type_obj.search([('code', '=', 'internal'), ('warehouse_id.company_id', '=', company_id)])
        if not types:
            types = type_obj.search([('code', '=', 'internal'), ('warehouse_id', '=', False)])
        return types[:1]

    date = fields.Date('Date', required=True, default=fields.Datetime.now )
    employee_id	= fields.Many2one('hr.employee', string='Checker', required=True, default=_default_employee )
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True, required=True, default="1" )
    warehouse_id = fields.Many2one(
            'stock.warehouse', 'Origin Warehouse')
    location_ids = fields.Many2many('stock.location', 'houtmeter_seed_stock_location_rel', 'houtmeter_seed_id', 'stock_location_id', 'Location')
    cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict", required=True, default=_default_cost_code_id )
    block_id = fields.Many2one('production.block', string='Block', ondelete="restrict", required=True, default=_default_block_id )
    vehicle_count = fields.Integer( string="Vehocle Count", required=True, default=5 )

    # @api.onchange('warehouse_id')	
    # def _change_wh(self):
    #     for order in self:
    #         location_ids = self.env['stock.location'].sudo().search([ ('location_id','=',order.warehouse_id.view_location_id.id ) ] )
    #         self.update({
    #             'location_ids': [( 6, 0, location_ids.ids )],
    #         })
                
    @api.multi
    def action_seed(self):   
        hourmeter = self.env['production.hourmeter.order'].create({
                "date" : self.date ,
                "employee_id" : self.employee_id.id ,
                "shift" : self.shift,
            })
        hourmeter_id = hourmeter.id
        sql = '''select id, driver_id from fleet_vehicle where id in ( select vehicle_tag_id from fleet_vehicle_vehicle_tag_rel where tag_id = 10 ) and driver_id is not null ORDER BY RANDOM() limit '''  + str( self.vehicle_count )
        self.env.cr.execute( sql )
        vehicle_ids = [ (x[0], x[1] ) for x in self.env.cr.fetchall()]
        location_ids = self.location_ids.ids
        # _logger.warning(self.location_ids)
        # return
        for vehicle_id in vehicle_ids:
            self.env['production.vehicle.hourmeter.log'].create({
                "hourmeter_order_id" : hourmeter_id ,
                "location_id" : location_ids[ random.randrange( 0, len( location_ids ) ) ]  ,
                "cost_code_id" : self.cost_code_id.id ,
                "block_id" : self.block_id.id ,
                "vehicle_id" : vehicle_id[0] ,
                "driver_id" : vehicle_id[1] ,
                "start" : 0 ,
                "end" : random.randrange( 1, 10 ) ,
                "state" : "draft",
            }).id
        hourmeter.action_confirm()
        hourmeter.action_done()
