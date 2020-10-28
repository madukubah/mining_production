# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class ProductionLosstimeAccumulation(models.Model):
    _name = 'production.losstime.accumulation'

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
    name = fields.Char(compute='_compute_name', store=True, string="Name")
    tag_id	= fields.Many2one('production.cop.tag', string='COP Tag', required=True )
    date = fields.Date('Date', help='' )
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    driver_id	= fields.Many2one('res.partner', string='Driver', required=True )
    losstime_type = fields.Selection([
		('slippery', 'Slippery'),
		('rainy', 'Rainy'),
        ], string='Losstime type', index=True, required=True )
    reference = fields.Char(string="Reference", size=100 )
    amount = fields.Float(string='Amount', default=0 )
    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
      required=True, readonly=True, copy=False, default='draft' )

    @api.depends( 'vehicle_id', 'date' )
    def _compute_name(self):
        for record in self:
            name = record.vehicle_id.name
            if not name:
                name = record.date
            elif record.date:
                name += ' / ' + record.date
            record.name = name

    @api.multi
    def post(self):
        for record in self:
            self.env['production.cop.tag.log'].sudo().create({
                    'cop_adjust_id' : record.cop_adjust_id.id,
                    'name' : record.date,
                    'date' : record.date,
                    # 'location_id' : record.location_id.id,
                    'tag_id' : record.tag_id.id,
                    'product_uom_qty' : 1,
                    # 'price_unit' : record.amount /record.ritase_count,
                    'price_unit' : record.amount, # TODO : change it programable
                    'amount' : record.amount,
                    'state' : 'posted',
                })
            record.write({'state' : 'posted' })