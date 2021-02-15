# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class ProductionActivityDefinition( models.Model ):
    _name = 'production.activity.definition'

    name = fields.Char(string="Name", size=100 , required=True, default="NEW")
    warehouse_id = fields.Many2one(
        'stock.warehouse', 'Origin Warehouse',
        required=True,
        ondelete="restrict" )
    warehouse_dest_id = fields.Many2one(
        'stock.warehouse', 'Destination Warehouse',
        required=True,
        ondelete="restrict" )
    active = fields.Boolean(
        'Active', default=True)

    @api.model
    def create(self, values):
        ProductionActivityDefinitionSudo = self.env['production.activity.definition'].sudo()
        activity_definition = ProductionActivityDefinitionSudo.search([ ( "active", "=", True ), ( "warehouse_id", "=", values["warehouse_id"] ), ( "warehouse_dest_id", "=", values["warehouse_dest_id"] ) ]) 
        if activity_definition :
            raise UserError(_('Only Create 1 file ( %s ).') % (activity_definition.name))

        res = super(ProductionActivityDefinition, self ).create(values)
        return res

    @api.multi
    def unlink(self):
        raise UserError(_("Cannot Delete Data, Please Archive It ") )