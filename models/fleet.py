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
    config_id	= fields.Many2one('production.config', string='Production Config' )

    @api.depends("product_id" )
    def _onset_product_id(self):
        for record in self:
            if( record.product_id.categ_id ):
                category = record.product_id.categ_id
                record.inventory_account_id = category.property_stock_valuation_account_id
        
class FleetVehicleLogServices(models.Model):
    _inherit = 'fleet.vehicle.log.services'
    
    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    product_uom_qty = fields.Integer( related='cost_id.product_uom_qty', string="Quantity", copy=True, default=1)
    price_unit = fields.Float(related='cost_id.price_unit', string='Price Unit', copy=True, default=0 )
    # cost_amount = fields.Float(related='cost_id.amount', string='Amount' )

    @api.onchange("product_uom_qty", "cost_subtype_id", "price_unit" )
    def _compute_amount(self):
        for record in self:
            if( record.cost_subtype_id.product_id ):
                product = record.cost_subtype_id.product_id
                # _logger.warning( product )
                record.price_unit = product.standard_price
                record.amount = record.price_unit * record.product_uom_qty
                
    @api.multi
    def post(self):
        super(FleetVehicleLogServices, self ).post()

class FleetVehicleCost(models.Model):
    _inherit = 'fleet.vehicle.cost'

    @api.model
    def _default_config(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0]

    production_config_id	= fields.Many2one('production.config', string='Production Config', default=_default_config )
    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    cost_subtype_id = fields.Many2one('fleet.service.type', 'Type', required=True, help='Cost type purchased with this cost')
    product_uom_qty = fields.Integer( string="Quantity", default=1)
    price_unit = fields.Float( string='Price Unit', default=0 )
    amount = fields.Float('Total Price', compute="_compute_amount")
    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )
    
    @api.depends("product_uom_qty", "price_unit" )
    def _compute_amount(self):
        for record in self:
            record.amount = record.price_unit * record.product_uom_qty

    @api.multi
    def post(self):
        for record in self:
            if record.cost_subtype_id.tag_id and record.state != 'posted' :
                self.env['production.cop.tag.log'].sudo().create({
                    'cop_adjust_id' : record.cop_adjust_id.id,
                    'name' : record.vehicle_id.name + ' / ' + record.cost_subtype_id.tag_id.name + ' / ' + record.date,
                    'date' : record.date,
                    'tag_id' : record.cost_subtype_id.tag_id.id,
                    'product_uom_qty' : record.product_uom_qty,
                    'price_unit' : record.price_unit,
                    'amount' : record.amount,
                    'state' : 'posted',
                })
            if record.cost_subtype_id in record.production_config_id.refuel_service_type_ids:
                record.create_fueling_log( )
            record.write({'state' : 'posted' })

    @api.multi
    def create_fueling_log(self):
        for record in self:
            self.env['fleet.vehicle.log.fuel'].sudo().create({
                    'cost_id' : record.id,
                    'cost_subtype_id' : record.cost_subtype_id.id,
                    'liter' : record.product_uom_qty,
                    'price_per_liter' : record.price_unit,
                })
            
    @api.model
    def create(self, values):
        service_type = self.env['fleet.service.type'].search( [ ( 'id', '=', values['cost_subtype_id'] ) ] )
        if not service_type.is_consumable :
            values["state"] = 'posted'
        res = super(FleetVehicleCost, self ).create(values)
        return res

class FleetVehicleLosstime(models.Model):
    _inherit = "fleet.vehicle.losstime"
    
    @api.model
    def _default_config(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0]

    production_config_id	= fields.Many2one('production.config', string='Production Config', default=_default_config )
    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )

    @api.multi
    def post(self):
        for record in self:
            record.write({'state' : 'posted' })