# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class ProductionConfig( models.Model ):
    _name = 'production.config'

    @api.model
    def _default_journal(self):
        journal_type = self.env.context.get('journal_type', False)
        company_id = self.env['res.company']._company_default_get('production.config').id
        if journal_type:
            journals = self.env['account.journal'].search([('type', '=', journal_type), ('company_id', '=', company_id)])
            if journals:
                return journals[0]
        return self.env['account.journal']


    name = fields.Char(string="Name", size=100 , required=True, default="NEW")
    company_id = fields.Many2one('res.company', string='Company', required=True,
        default=lambda self: self.env.user.company_id)
    # mining
    lot_id = fields.Many2one(
        'stock.production.lot', 'Default Production Lot',
		required=True, 
        )
    enable_default_lot = fields.Boolean(
        'Enable Default Lot', default=True )
    main_product_id = fields.Many2one('product.product', string='Main Materials', related="lot_id.product_id" )
    waste_product_ids = fields.Many2many('product.product', 'production_config_waste_product_rel', 'config_id', 'product_id', string='Waste Materials' )
    product_ids = fields.Many2many('product.product', 'production_config_product_rel', 'config_id', 'product_id', string='Materials' )
    other_product_ids = fields.Many2many('product.product', 'production_config_other_product_rel', 'config_id', 'product_id', string='Other Materials' )
    # accounting
    journal_type = fields.Selection(related='cop_journal_id.type', help="Technical field used for usability purposes" )
    cop_journal_id = fields.Many2one('account.journal', string='COP Journal', default=_default_journal, required=True )
    cop_cost_credit_account_id = fields.Many2one('account.account', string='COP Cost Credit Account', required=True )
    product_categ_id = fields.Many2one('product.category', string='Material Category', required=True, related="main_product_id.categ_id" )
    valuation_account_id = fields.Many2one('account.account', string='Valuation Account', required=True, related="product_categ_id.property_stock_valuation_account_id" )
    # UoM
    main_uom_id = fields.Many2one('product.uom', string='Main UoM', related="main_product_id.uom_id" )
    rit_count_uom_ids = fields.Many2many('product.uom', 'config_rit_count_uom_rel', 'config_id', 'uom_id', string='Ritase Count UoMs' )
    bucket_count_uom_ids = fields.Many2many('product.uom', 'config_bucket_count_uom_rel', 'config_id', 'uom_id', string='Bucket Count UoMs' )
    # factors
    factor_density_ids = fields.One2many(
        'production.config.factor.density',
        'config_id',
        string='Densities',
        copy=True )
    # vehicle
    vehicle_model_ids = fields.Many2many('fleet.vehicle.model', 'config_vehicle_model_rel', 'config_id', 'model_id', string='Mining Unit Models ' )
    refuel_service_type_ids = fields.Many2many('fleet.service.type', 'config_service_type_rel', 'config_id', 'service_type_id', string='Refuel Service Types' )
    categ_ids = fields.Many2many('product.category', 'config_product_category_rel', 'config_id', 'categ_id', string='Item Service Category' )
    # rit
    rit_tag_id	= fields.Many2one('production.cop.tag', string='Ritase COP Tag', required=True )
    rit_losstime_tag_id	= fields.Many2one('production.cop.tag', string='Losstime COP Tag', required=True )
    rit_price_unit = fields.Float('Price Per Ritase', required=True, default=0 )
    rit_minimal_cash = fields.Float('Minimal Cash For Losstime', required=True, default=0 )
    rit_vehicle_tag_id = fields.Many2one('fleet.vehicle.tag', 'Ritase Vehicle Tag', required=True )
    # hm
    hm_tag_id	= fields.Many2one('production.cop.tag', string='Hourmeter COP Tag', required=True )
    hm_losstime_tag_id	= fields.Many2one('production.cop.tag', string='Losstime COP Tag', required=True )
    hm_price_unit = fields.Float('Price Per Hourmeter', required=True, default=0 )
    hm_minimal_cash = fields.Float('Minimal Cash For Losstime', required=True, default=0 )
    hm_vehicle_tag_id = fields.Many2one('fleet.vehicle.tag', 'Hourmeter Vehicle Tag', required=True )
    # wt
    wt_tag_id	= fields.Many2one('production.cop.tag', string='Water Truck COP Tag', required=True )
    wt_losstime_tag_id	= fields.Many2one('production.cop.tag', string='Losstime COP Tag', required=True )
    wt_price_unit = fields.Float('Price Per Ritase', required=True, default=0 )
    wt_minimal_cash = fields.Float('Minimal Cash For Losstime', required=True, default=0 )
    wt_vehicle_tag_id = fields.Many2one('fleet.vehicle.tag', 'Water Truck Vehicle Tag', required=True )

    
    active = fields.Boolean(
        'Active', default=True,
        help="If unchecked, it will allow you to hide the rule without removing it.")
    
    @api.model
    def create(self, values):
        ProductionConfigSudo = self.env['production.config'].sudo()
        # production_config = ProductionConfigSudo.search([ ( "active", "=", True ) ]) 
        production_config = ProductionConfigSudo.search([]) 
        if production_config :
                raise UserError(_('Only Create 1 file ( %s ).') % (production_config.name))

        res = super(ProductionConfig, self ).create(values)
        return res
    
    @api.multi
    def unlink(self):
        raise UserError(_("Cannot Delete Data, Please Archive It ") )

class ProductionConfigFactorDensity( models.Model ):
    _name = 'production.config.factor.density'

    config_id = fields.Many2one('production.config' )
    product_id = fields.Many2one('product.product', string='Material', required=True)
    density_id = fields.Many2one('qaqc.density', string='Material Density', required=True)
    density = fields.Float('Density', related="density_id.density", required=True, default=0 )
    density_factor = fields.Float('Density Factor', required=True, default=1 )

class ProductionActivityDefinition( models.Model ):
    _name = 'production.activity.definition'

    name = fields.Char(string="Name", size=100 , required=True, default="NEW")
    warehouse_id = fields.Many2one(
            'stock.warehouse', 'Origin Warehouse',
            ondelete="restrict" )
    warehouse_dest_id = fields.Many2one(
			'stock.warehouse', 'Destination Warehouse',
			ondelete="restrict" )
