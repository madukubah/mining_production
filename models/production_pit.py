# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Pit(models.Model):
    _name = "production.pit"
    
    name = fields.Char(string="Name", size=100 , required=True )
    warehouse_id = fields.Many2one(
            'stock.warehouse', 'Warehouse',
			required=True,
            ondelete="restrict")
    location_id = fields.Many2one(
            'stock.location', 'Location',
			readonly=True,
			domain=[ ('usage','=',"internal")  ],
            ondelete="restrict")
    active = fields.Boolean(
        'Active', default=True,
        help="If unchecked, it will allow you to hide the rule without removing it.")
    
    @api.model
    def create(self, values):
        StockLocation = self.env['stock.location'].sudo()
        StockPickingType = self.env['stock.picking.type'].sudo()
        StockWarehouse = self.env['stock.warehouse'].sudo()

        warehouse = StockWarehouse.search([ ("id", '=', values["warehouse_id"] ) ])
        picking_type = StockPickingType.search([ ("code", '=', "outgoing" ), ("warehouse_id", '=', values["warehouse_id"] ) ])
        if not picking_type:
            raise UserError(_("Cannot Find Picking Type For Procurement Rule ") )

        values["location_id"] = StockLocation.create({
                            "name" : values["name"],
                            "usage" : "internal",
                            "location_id" : warehouse.view_location_id.id ,
                        }).id

        res = super(Pit, self ).create(values)
        return res
	
    @api.multi
    def unlink(self):
        raise UserError(_("Cannot Delete Data, Please Archive It ") )
        # for rec in self:
        #     if rec.location_id:
        #         rec.location_id.toggle_active()
        
        # return super(Pit, self ).unlink()