# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class FleetServiceType(models.Model):
    _inherit = 'fleet.service.type'

    is_consumable	=  fields.Boolean(string="Is Consumable",default=False )
    product_id = fields.Many2one(
        'product.product', 'Product',
        domain=[('type', 'in', ['product', 'consu'])]
        )
    inventory_account_id = fields.Many2one('account.account', 
        string='Inventory Account', 
        compute='_onset_product_id', 
        domain=[('deprecated', '=', False)], 
        )
    tag_id	= fields.Many2one('production.cop.tag', string='Tag' )
    

    @api.depends("product_id" )
    def _onset_product_id(self):
        for rec in self:
            if( rec.product_id.categ_id ):
                category = rec.product_id.categ_id
                rec.inventory_account_id = category.property_stock_valuation_account_id
        
class FleetVehicleLogServices(models.Model):
    _inherit = 'fleet.vehicle.log.services'
    
    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    product_uom_qty = fields.Integer( related='cost_id.product_uom_qty', string="Quantity", default=1)
    cost_amount = fields.Float(related='cost_id.amount', string='Amount' )

    @api.onchange("product_uom_qty", "cost_subtype_id" )
    def _compute_amount(self):
        for rec in self:
            if( rec.cost_subtype_id.product_id ):
                product = rec.cost_subtype_id.product_id
                _logger.warning( product )
                rec.amount = product.standard_price * rec.product_uom_qty
                
    @api.multi
    def post(self):
        super(FleetVehicleLogServices, self ).post()

class FleetVehicleCost(models.Model):
    _inherit = 'fleet.vehicle.cost'

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    product_uom_qty = fields.Integer( string="Quantity", default=1)
    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )
    
    @api.multi
    def post(self):
        for record in self:
            if record.cost_subtype_id.tag_id :
                self.env['production.cop.tag.log'].sudo().create({
                    'cop_adjust_id' : record.cop_adjust_id.id,
                    'name' : record.vehicle_id.name + ' / ' + record.cost_subtype_id.tag_id.name + ' / ' + record.date,
                    'date' : record.date,
                    'tag_id' : record.cost_subtype_id.tag_id.id,
                    'product_uom_qty' : record.product_uom_qty,
                    'price_unit' : record.amount / record.product_uom_qty,
                    'amount' : record.amount,
                    'state' : 'posted',
                })

            record.write({'state' : 'posted' })
    
    @api.model
    def create(self, values):
        service_type = self.env['fleet.service.type'].search( [ ( 'id', '=', values['cost_subtype_id'] ) ] )
        if not service_type.is_consumable :
            values["state"] = 'posted'
        res = super(FleetVehicleCost, self ).create(values)
        return res
