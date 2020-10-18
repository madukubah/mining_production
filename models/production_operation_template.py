# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time

import logging
_logger = logging.getLogger(__name__)

class ProductionOperationTemplate(models.Model):
    _name = "production.operation.template"
    
    name = fields.Char(compute='_compute_name', store=True)
    date = fields.Date('Date', help='' )
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True )
    location_id = fields.Many2one(
            'stock.location', 'Location',
			domain=[ ('usage','=',"internal")  ],
            ondelete="restrict" )
    cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict", required=True )
    block_id = fields.Many2one('production.block', string='Block', ondelete="restrict", required=True )
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    driver_id	= fields.Many2one('res.partner', string='Driver', required=True )

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
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
            record.write({'state' : 'posted' })

    @api.onchange('vehicle_id')	
    def _change_vehicle_id(self):
        for record in self:
            record.driver_id = record.vehicle_id.driver_id


