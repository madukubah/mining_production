# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time

import logging
_logger = logging.getLogger(__name__)

class ProductionCopAdjust(models.Model):
    _name = "production.cop.adjust"
    _order = "id desc"
    
    READONLY_STATES = {
        'draft': [('readonly', False)],
        'confirm': [('readonly', True)],
        'done': [('readonly', True)],
        'cancel': [('readonly', True)],
    }

    name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
    company_id = fields.Many2one(
        'res.company', 'Company',
        default=lambda self: self.env['res.company']._company_default_get('production.order'),
        required=True)
    date = fields.Date('Date', help='',default=time.strftime("%Y-%m-%d"), states=READONLY_STATES )
    employee_id	= fields.Many2one('hr.employee', string='Responsible', states=READONLY_STATES )
    cost_ids = fields.One2many('fleet.vehicle.cost', 'cop_adjust_id', 'Vehicle Costs', states=READONLY_STATES )

    state = fields.Selection([
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('done', 'Posted'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')
        
    @api.model
    def create(self, values):
        seq = self.env['ir.sequence'].next_by_code('cop_adjust')
        values["name"] = seq
        res = super(ProductionCopAdjust, self ).create(values)
        return res
    
    @api.multi
    def action_settle(self):
        self.ensure_one()
        self.action_reload()
        self._settle_vehicle_cost()

    @api.multi
    def action_reload(self):
        for record in self:
            if record.state == 'done':
                continue

            record._reload()
    
    @api.multi
    def _reload(self):
        VehicleCost = self.env['fleet.vehicle.cost'].sudo()
        vehicle_costs = VehicleCost.search( [ ( "date", "<=", self.date ), ( "state", "=", "draft" ) ] )
        vehicle_costs_ids = [ vehicle_cost.id for vehicle_cost in vehicle_costs if vehicle_cost.cost_subtype_id.is_consumable ]
        self.update({
            'cost_ids': [( 6, 0, vehicle_costs_ids )],
        })
        return True

    @api.multi
    def _settle_vehicle_cost(self):
        self.ensure_one()

        product_n_qty_list = {}
        LogServices = self.env['fleet.vehicle.log.services'].sudo()
        services = LogServices.search( [ ("cost_id", "in", [cost.id for cost in self.cost_ids ] )] )
        
        for service in services:
            if( service.cost_subtype_id.is_consumable and service.cost_subtype_id.product_id ) :
                product = service.cost_subtype_id.product_id
                if product_n_qty_list.get( product.id , False):
                    product_n_qty_list[ product.id ]['qty'] += service.product_uom_qty
                else : 
                    product_n_qty_list[ product.id ] = {
                        'cost_subtype_id' : service.cost_subtype_id,
                        'qty' : service.product_uom_qty,
                    }
        
        for product_id, obj in product_n_qty_list.items():
            self._generate_moves( product_id, obj['qty'] )
            self._account_entry_move( obj['cost_subtype_id'], obj['qty'] )
            
        self.cost_ids.post()
        self.write({ 'state' : 'done' })
        
    
    def _generate_moves(self, product_id, qty):
        product = self.env['product.product'].search( [ ("id", "=", product_id ) ] )
        
        domain_quant = [ ("product_id", "=", product_id ), ("location_id.usage", "=", "internal" ) ]
        stock_quants = self.env['stock.quant'].read_group( domain_quant, [ 'location_id', 'product_id', 'qty'], ["location_id", 'product_id'], orderby='id')
        location_id = None
        for stock_quant in stock_quants:
            _logger.warning( stock_quant )
            if stock_quant['qty'] >= qty :
                location_id = stock_quant['location_id']
                break

        if not location_id :
            raise UserError(_('No enough Quantity for product %s in any location to remove') % (product.name))

        move = self.env['stock.move'].create({
            'name': self.name,
            'date': self.date,
            'product_id': product[0].id,
            'product_uom': product[0].uom_id.id,
            'product_uom_qty': qty,
            'location_id': location_id[0], # ? set location in service type
            'location_dest_id': product[0].property_stock_production.id,
            'move_dest_id': False,
            'procurement_id': False,
            'company_id': self.company_id.id,
            'origin': self.name,
        })
        
        move.action_confirm()
        move.action_done()
        return move
    
    def _account_entry_move(self, costs_subtype, qty):
        """ Accounting COP Entries """
        journal_id, acc_src, acc_dest, cop_account_id = costs_subtype._get_accounting_data_for_cop()
        self.with_context(force_company=self.company_id.id)._create_account_move_line(costs_subtype, qty , acc_dest, cop_account_id, journal_id)

        # if self.company_id.anglo_saxon_accounting:
        #     # Creates an account entry from stock_input to stock_output on a dropship move. https://github.com/odoo/odoo/issues/12687
        #     journal_id, acc_src, acc_dest, acc_valuation = move._get_accounting_data_for_valuation()
        #     if move.location_id.usage == 'supplier' and move.location_dest_id.usage == 'customer':
        #         self.with_context(force_company=move.company_id.id)._create_account_move_line(move, acc_src, acc_dest, journal_id)
        #     if move.location_id.usage == 'customer' and move.location_dest_id.usage == 'supplier':
        #         self.with_context(force_company=move.company_id.id)._create_account_move_line(move, acc_dest, acc_src, journal_id)

    def _create_account_move_line(self, costs_subtype, qty , credit_account_id, debit_account_id, journal_id):
       
        AccountMove = self.env['account.move']
        move_lines = self._prepare_account_move_line( costs_subtype.product_id, qty, costs_subtype.product_id.standard_price , credit_account_id, debit_account_id)
        if move_lines:
            date = self._context.get('force_period_date', fields.Date.context_today(self))
            new_account_move = AccountMove.create({
                'journal_id': journal_id,
                'line_ids': move_lines,
                'date': date,
                'ref': self.name})
            new_account_move.post()

    def _prepare_account_move_line(self, product, qty, cost, credit_account_id, debit_account_id):
        """
        Generate the account.move.line values to post to track the stock valuation difference due to the
        processing of the given quant.
        """
        self.ensure_one()

        if self._context.get('force_valuation_amount'):
            valuation_amount = self._context.get('force_valuation_amount')
        else:
            if product.cost_method == 'average':
                valuation_amount = cost if product.cost_method == 'real' else product.standard_price
        # the standard_price of the product may be in another decimal precision, or not compatible with the coinage of
        # the company currency... so we need to use round() before creating the accounting entries.
        debit_value = self.company_id.currency_id.round(valuation_amount * qty)

        # check that all data is correct
        if self.company_id.currency_id.is_zero(debit_value):
            if product.cost_method == 'standard':
                raise UserError(_("The found valuation amount for product %s is zero. Which means there is probably a configuration error. Check the costing method and the standard price") % (product.name,))
            return []
        credit_value = debit_value

        # if product.cost_method == 'average' and self.company_id.anglo_saxon_accounting:
        #     # in case of a supplier return in anglo saxon mode, for products in average costing method, the stock_input
        #     # account books the real purchase price, while the stock account books the average price. The difference is
        #     # booked in the dedicated price difference account.
        #     if self.location_dest_id.usage == 'supplier' and self.origin_returned_move_id and self.origin_returned_move_id.purchase_line_id:
        #         debit_value = self.origin_returned_move_id.price_unit * qty
        #     # in case of a customer return in anglo saxon mode, for products in average costing method, the stock valuation
        #     # is made using the original average price to negate the delivery effect.
        #     if self.location_id.usage == 'customer' and self.origin_returned_move_id:
        #         debit_value = self.origin_returned_move_id.price_unit * qty
        #         credit_value = debit_value
        partner_id = False #(self.picking_id.partner_id and self.env['res.partner']._find_accounting_partner(self.picking_id.partner_id).id) or False
        debit_line_vals = {
            'name': self.name,
            'product_id': product.id,
            'quantity': qty,
            'product_uom_id': product.uom_id.id,
            'ref': self.name,
            'partner_id': partner_id,
            'debit': debit_value if debit_value > 0 else 0,
            'credit': -debit_value if debit_value < 0 else 0,
            'account_id': debit_account_id,
        }
        credit_line_vals = {
            'name': self.name,
            'product_id': product.id,
            'quantity': qty,
            'product_uom_id': product.uom_id.id,
            'ref': self.name,
            'partner_id': partner_id,
            'credit': credit_value if credit_value > 0 else 0,
            'debit': -credit_value if credit_value < 0 else 0,
            'account_id': credit_account_id,
        }
        res = [(0, 0, debit_line_vals), (0, 0, credit_line_vals)]
        if credit_value != debit_value:
            # for supplier returns of product in average costing method, in anglo saxon mode
            diff_amount = debit_value - credit_value
            price_diff_account = product.property_account_creditor_price_difference
            if not price_diff_account:
                price_diff_account = product.categ_id.property_account_creditor_price_difference_categ
            if not price_diff_account:
                raise UserError(_('Configuration error. Please configure the price difference account on the product or its category to process this operation.'))
            price_diff_line = {
                'name': self.name,
                'product_id': product.id,
                'quantity': qty,
                'product_uom_id': product.uom_id.id,
                'ref': self.name,
                'partner_id': partner_id,
                'credit': diff_amount > 0 and diff_amount or 0,
                'debit': diff_amount < 0 and -diff_amount or 0,
                'account_id': price_diff_account.id,
            }
            res.append((0, 0, price_diff_line))
        return res