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

    product_uom = fields.Many2one(
            'product.uom', 'Product Unit of Measure', 
			domain=[ ('category_id.name','=',"Mining")  ],
            default=lambda self: self._context.get('product_uom', False),
			)
    bucket = fields.Integer( string="Bucket", default=0 )
    
    @api.multi
    def action_seed(self):  
        ritase_orders = self.env['production.ritase.order'].search([])
        ritase_orders.syncronize()
        for ritase_order in ritase_orders:
            if ritase_order.old_product_uom.id == self.product_uom.id and self.bucket != 0 :
                ritase_order.syncronize()
                ritase_order.bucket = self.bucket
                ritase_order.counter_ids.set_bucket( self.bucket )
                ritase_order.lot_move_ids.set_bucket( self.bucket )