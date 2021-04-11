# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time
import logging
_logger = logging.getLogger(__name__)


class ProductionCopTag(models.Model):
    _name = "production.cop.tag"
    
    name = fields.Char(string="Name", required=True )
    is_consumable	=  fields.Boolean(string="Is Stockable",default=False )
    product_id = fields.Many2one(
        'product.product', 'Product',
        domain=[('type', 'in', ['product', 'consu'])]
        )
    inventory_account_id = fields.Many2one('account.account', 
        string='Inventory Account', 
        compute='_onset_product_id', 
        domain=[('deprecated', '=', False)], 
        )
    
    
    @api.depends("product_id" )
    def _onset_product_id(self):
        for record in self:
            if( record.product_id.categ_id ):
                category = record.product_id.categ_id
                record.inventory_account_id = category.property_stock_valuation_account_id
    
    @api.multi
    def _get_accounting_data(self):
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

class ProductionCopTagLog(models.Model):
    _name = "production.cop.tag.log"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'date desc'
    
    READONLY_STATES = {
        'draft': [('readonly', False)],
        'posted': [('readonly', True)],
    }

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    name = fields.Char(compute='_compute_name', store=True , states=READONLY_STATES)
    location_id = fields.Many2one(
            'stock.location', 'Location',
            domain=[ ('usage','=',"internal") ],
            ondelete="restrict", states=READONLY_STATES )
    date = fields.Date('Date', help='',default=fields.Datetime.now,required=True, states=READONLY_STATES )
    tag_id	= fields.Many2one('production.cop.tag', string='Tag',required=True, states=READONLY_STATES )
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', readonly=True )
    product_id = fields.Many2one(
        'product.product', 'Product',
        domain=[('type', 'in', ['product', 'consu'])], 
        ondelete="cascade",
        )
    product_uom_qty = fields.Integer( string="Quantity", required=True, default=1)
    price_unit = fields.Float( string="Price Unit", required=True, default=1)
    amount = fields.Float( string='Amount', compute="_compute_amount", required=True,states=READONLY_STATES )
    remarks = fields.Char( string='Remarks', states=READONLY_STATES )

    from_cop_adjust	=  fields.Boolean(string="Is From COP Adjust" ,default=False )

    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )

    @api.onchange('tag_id')	
    def _domain_product(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        categ_ids = [ x.id for x in production_config[0].categ_ids ]
        product_ids = self.env['product.product'].sudo(  ).search( [ ("categ_id", "in", categ_ids ) ] )
        return {
                'domain':{
                    'product_id':[('id','in', product_ids.ids )] ,
                    }
                }

    @api.onchange( "product_id" )
    def _onchange_product(self):
        for record in self:
            if record.product_id :
                record.price_unit = record.product_id.standard_price

    @api.onchange("tag_id" )
    def _onchange_tag_id(self):
        for record in self:
            if( record.product_id ):
                product = record.product_id
                record.price_unit = product.standard_price
            elif( record.tag_id.product_id ):
                product = record.tag_id.product_id
                record.product_id = product
                record.price_unit = product.standard_price

            
    @api.depends("product_uom_qty", "price_unit" )
    def _compute_amount(self):
        for record in self:
            record.amount = record.price_unit * record.product_uom_qty

    @api.depends('tag_id', 'date')
    def _compute_name(self):
        for record in self:
            name = record.tag_id.name
            if not name:
                name = record.date
            elif record.date:
                name += ' / ' + record.date
            record.name = name

    @api.multi
    def post(self):
        for record in self:
            record.write({'state' : 'posted' })
    
    @api.multi
    def unlink(self):
        for order in self:
            if order.state in [ "posted"] :
                raise UserError(_('Cannot delete file which is in state \'%s\'.') %(order.state,))
        return super(ProductionCopTagLog, self).unlink()

    @api.model
    def create(self, values):
        service_type = self.env['fleet.service.type'].search( [ ( 'tag_id', '=', values['tag_id'] ) ] )
        # if service_type and not values.get( 'cop_adjust_id' , False) :
        if service_type and not values.get( 'from_cop_adjust' , False) :
            raise UserError(_('Cannot Create Log From This Form, Please Create It In Vehicle Service Log'))
            
        res = super(ProductionCopTagLog, self ).create(values)
        return res