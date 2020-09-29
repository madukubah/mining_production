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
        
    cop_account_id = fields.Many2one('account.account', 
        string='COP Account', 
        domain=[('deprecated', '=', False)], 
        )

    @api.depends("product_id" )
    def _onset_product_id(self):
        for rec in self:
            if( rec.product_id.categ_id ):
                category = rec.product_id.categ_id
                rec.inventory_account_id = category.property_stock_valuation_account_id
    
    @api.multi
    def _get_accounting_data_for_cop(self):
        """ Return the accounts and journal to use to post Journal Entries for
        the real-time valuation of the quant. """
        self.ensure_one()
        accounts_data = self.product_id.product_tmpl_id.get_product_accounts()
        acc_src = accounts_data['stock_input'].id
        acc_dest = accounts_data['stock_output'].id

        if not accounts_data.get('stock_journal', False):
            raise UserError(_('You don\'t have any stock journal defined on your product category, check if you have installed a chart of accounts'))
        if not acc_src:
            raise UserError(_('Cannot find a stock input account for the product %s. You must define one on the product category, or on the location, before processing this operation.') % (self.product_id.name))
        if not acc_dest:
            raise UserError(_('Cannot find a stock output account for the product %s. You must define one on the product category, or on the location, before processing this operation.') % (self.product_id.name))
        if not self.cop_account_id:
            raise UserError(_('You don\'t have any COP account defined on your Service typ. You must define one before processing this operation.'))
        journal_id = accounts_data['stock_journal'].id
        return journal_id, acc_src, acc_dest, self.cop_account_id.id

class FleetVehicleLogServices(models.Model):
    _inherit = 'fleet.vehicle.log.services'
    
    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    product_uom_qty = fields.Integer( string="Quantity", default=1)
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
        for record in self:
            record.write({'state' : 'posted' })

class FleetVehicleCost(models.Model):
    _inherit = 'fleet.vehicle.cost'

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )
    
    @api.multi
    def post(self):
        for record in self:
            record.write({'state' : 'posted' })
    
    @api.model
    def create(self, values):
        service_type = self.env['fleet.service.type'].search( [ ( 'id', '=', values['cost_subtype_id'] ) ] )
        if not service_type.is_consumable :
            values["state"] = 'posted'
        res = super(FleetVehicleCost, self ).create(values)
        return res
