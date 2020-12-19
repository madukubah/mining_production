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
    lot_id = fields.Many2one(
        'stock.production.lot', 'Default Production Lot',
		required=True, 
        )
    cop_journal_id = fields.Many2one('account.journal', string='COP Journal', default=_default_journal, required=True )
    cop_cost_credit_account_id = fields.Many2one('account.account', string='COP Cost Credit Account', required=True )
    journal_type = fields.Selection(related='cop_journal_id.type', help="Technical field used for usability purposes" )

    rit_tag_id	= fields.Many2one('production.cop.tag', string='Ritase COP Tag', required=True )
    rit_losstime_tag_id	= fields.Many2one('production.cop.tag', string='Losstime COP Tag', required=True )
    rit_price_unit = fields.Float('Price Per Ritase', required=True, default=0 )
    rit_minimal_cash = fields.Float('Minimal Cash For Losstime', required=True, default=0 )
    rit_vehicle_tag_id = fields.Many2one('fleet.vehicle.tag', 'Ritase Vehicle Tag', required=True )

    hm_tag_id	= fields.Many2one('production.cop.tag', string='Hourmeter COP Tag', required=True )
    hm_losstime_tag_id	= fields.Many2one('production.cop.tag', string='Losstime COP Tag', required=True )
    hm_price_unit = fields.Float('Price Per Hourmeter', required=True, default=0 )
    hm_minimal_cash = fields.Float('Minimal Cash For Losstime', required=True, default=0 )
    hm_vehicle_tag_id = fields.Many2one('fleet.vehicle.tag', 'Hourmeter Vehicle Tag', required=True )
    
    refuel_service_type_ids = fields.Many2many('fleet.service.type', 'config_service_type_rel', 'config_id', 'service_type_id', string='Refuel Service Types' )

    active = fields.Boolean(
        'Active', default=True,
        help="If unchecked, it will allow you to hide the rule without removing it.")
    
    @api.model
    def create(self, values):
        ProductionConfigSudo = self.env['production.config'].sudo()
        production_config = ProductionConfigSudo.search([ ( "active", "=", True ) ]) 
        if production_config :
                raise UserError(_('Only Create 1 file ( %s ).') % (production_config.name))

        res = super(ProductionConfig, self ).create(values)
        return res