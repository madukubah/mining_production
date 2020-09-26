# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class MiningProductionConfig(models.Model):
    _name = 'mining.production.config'

    name = fields.Char(string="Name", size=100 , required=True, default="NEW")
    company_id = fields.Many2one('res.company', string='Company', required=True,
        default=lambda self: self.env.user.company_id)
    lot_id = fields.Many2one(
        'stock.production.lot', 'Default Production Lot',
		required=True, 
        )

    active = fields.Boolean(
        'Active', default=True,
        help="If unchecked, it will allow you to hide the rule without removing it.")
    
    @api.model
    def create(self, values):
        ProductionConfig = self.env['mining.production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if production_config :
                raise UserError(_('Only Create 1 file ( %s ).') % (production_config.name))

        res = super(MiningProductionConfig, self ).create(values)
        return res