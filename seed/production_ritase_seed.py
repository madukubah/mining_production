# -*- coding: utf-8 -*-

import logging
import random
import time
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from calendar import monthrange
_logger = logging.getLogger(__name__)

class ProductionRitaseSeed(models.TransientModel):
    _name = 'production.ritase.seed'

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

    date = fields.Date('Date', required=True, default=time.strftime("%Y-%m-%d %H:%M:%S") )
    employee_id	= fields.Many2one('hr.employee', string='Checker', required=True, default=_default_employee )
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True, required=True, default="1" )
    warehouse_id = fields.Many2one(
            'stock.warehouse', 'Origin Warehouse')
    warehouse_dest_id = fields.Many2one(
			'stock.warehouse', 'Destination Warehouse')
    location_ids = fields.Many2many('stock.location', 'ritase_seed_stock_location_rel', 'ritase_seed_id', 'stock_location_id', 'Location')
    location_dest_ids = fields.Many2many('stock.location', 'ritase_seed_stock_location_dest_rel', 'ritase_seed_id', 'stock_location_id', 'Location Dest')
    product_id = fields.Many2one('product.product', 'Material', domain=[ ('type','=','product' ) ], required=True)
    product_uom = fields.Many2one(
            'product.uom', 'Product Unit of Measure', 
            required=True,
			domain=[ ('category_id.name','=',"Mining")  ],
            default=lambda self: self._context.get('product_uom', False)
			)
    load_vehicle_id = fields.Many2one('fleet.vehicle', 'Load Unit', required=True , default=_default_load_vehicle_id )
    pile_vehicle_id = fields.Many2one('fleet.vehicle', 'Pile Unit', required=True , default=_default_pile_vehicle_id )
    picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To', required=True, default=_default_picking_type,\
		help="This will determine picking type of internal shipment")
    cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict", required=True, default=_default_cost_code_id )
    block_id = fields.Many2one('production.block', string='Block', ondelete="restrict", required=True, default=_default_block_id )

    @api.onchange('warehouse_id', "warehouse_dest_id")	
    def _change_wh(self):
        for order in self:
            return {
                'domain':{
                    'location_id':[('location_id','=',order.warehouse_id.view_location_id.id )] ,
                    'location_dest_id':[('location_id','=',order.warehouse_dest_id.view_location_id.id )]
                    } 
                }
                
    @api.multi
    def action_seed(self):   
        
        for location_id in self.location_ids:
            offset = 0
            for location_dest_id in self.location_dest_ids:
                _logger.warning(location_id.id)
                _logger.warning(location_dest_id.id)
                ritase = self.env['production.ritase.order'].create({
                    "date" : self.date ,
                    "employee_id" : self.employee_id.id ,
                    "warehouse_id" : self.warehouse_id.id ,
                    "warehouse_dest_id" : self.warehouse_dest_id.id ,
                    "location_id" : location_id.id ,
                    "location_dest_id" : location_dest_id.id ,
                    "product_id" : self.product_id.id,
                    "product_uom" : self.product_uom.id,
                    "load_vehicle_id" : self.load_vehicle_id.id,
                    "pile_vehicle_id" : self.pile_vehicle_id.id,
                    "pile_vehicle_id" : self.pile_vehicle_id.id,
                    "shift" : self.shift,
                    "picking_type_id" : self.picking_type_id.id,
                })
                ritase_id = ritase.id
                _logger.warning( ritase_id )
                _logger.warning( '''select id, driver_id from fleet_vehicle where id in ( select vehicle_tag_id from fleet_vehicle_vehicle_tag_rel where tag_id = 9 ) and driver_id is not null ORDER BY RANDOM() limit 3 offset %s''', offset )
                sql = '''select id, driver_id from fleet_vehicle where id in ( select vehicle_tag_id from fleet_vehicle_vehicle_tag_rel where tag_id = 9 ) and driver_id is not null ORDER BY RANDOM() limit 3 offset ''' + str( offset )
                self.env.cr.execute( sql )
                vehicle_ids = [ (x[0], x[1] ) for x in self.env.cr.fetchall()]
                counts = 0
                for vehicle_id in vehicle_ids:
                    ritase_counter_id = self.env['production.ritase.counter'].create({
                        "ritase_order_id" : ritase_id ,
                        "cost_code_id" : self.cost_code_id.id ,
                        "block_id" : self.block_id.id ,
                        "vehicle_id" : vehicle_id[0] ,
                        "driver_id" : vehicle_id[1] ,
                        "state" : "draft",
                    }).id
                    for i in range(1, random.randrange( 10, 20 )  ):
                        counts +=1
                        self.env['production.ritase.log'].create({
                            "counter_id" : ritase_counter_id ,
                            "datetime" : time.strftime("%Y-%m-%d %H:%M:%S")  ,
                        })
                
                ProductionConfig = self.env['production.config'].sudo()
                production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
                if not production_config :
                    raise UserError(_('Please Set Configuration file') )

                self.env['production.ritase.lot.move'].create({
                        "ritase_order_id" : ritase_id ,
                        "lot_id" : production_config[0].lot_id.id,
                        "ritase_count" : counts
                    })
                offset += 3
                ritase._compute_ritase_count()
                ritase.action_confirm()