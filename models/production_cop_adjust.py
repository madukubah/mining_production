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
    production_config_id	= fields.Many2one('mining.production.config', string='Production Config', states=READONLY_STATES )
    cost_ids = fields.One2many('fleet.vehicle.cost', 'cop_adjust_id', 'Vehicle Costs', states=READONLY_STATES )
    tag_log_ids = fields.One2many('production.cop.tag.log', 'cop_adjust_id', 'COP Tagging', states=READONLY_STATES )
    rit_ids = fields.One2many('mining.dumptruck.activity', 'cop_adjust_id', 'Ritase Costs', states=READONLY_STATES )
    hourmeter_ids = fields.One2many('production.vehicle.hourmeter.log', 'cop_adjust_id', 'Hourmeter Costs', states=READONLY_STATES )

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
        ProductionConfig = self.env['mining.production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Default Configuration file') )
        if not production_config.lot_id :
            raise UserError(_('Please Set Default Lot Product Configuration file') )
        if not production_config.cop_journal_id :
            raise UserError(_('Please Set Default COP Journal Configuration file') )
        values["production_config_id"] = production_config.id
        res = super(ProductionCopAdjust, self ).create(values)
        return res
    
    @api.multi
    def action_settle(self):
        self.ensure_one()
        self.action_reload()
        self._settle_cost()

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

        DumptruckActivity = self.env['mining.dumptruck.activity'].sudo()
        dumptruck_activity = DumptruckActivity.search( [ ( "date", "<=", self.date ), ( "state", "=", "draft" ) ] )
        self.update({
            'rit_ids': [( 6, 0, dumptruck_activity.ids )],
        })

        HourmeterLog = self.env['production.vehicle.hourmeter.log'].sudo()
        hourmeter_log = HourmeterLog.search( [ ( "date", "<=", self.date ), ( "state", "=", "draft" ) ] )
        self.update({
            'hourmeter_ids': [( 6, 0, hourmeter_log.ids )],
        })

        CopTagLog = self.env['production.cop.tag.log'].sudo()
        tag_log = CopTagLog.search( [ ( "date", "<=", self.date ), ( "state", "=", "draft" ) ] )
        self.update({
            'tag_log_ids': [( 6, 0, tag_log.ids )],
        })
        return True
    
    @api.multi
    def _update_ore_valuation(self):
        self.ensure_one()


    @api.multi
    def _settle_cost(self):
        self.ensure_one()

        product_n_qty_list = {}
        LogServices = self.env['fleet.vehicle.log.services'].sudo()
        services = LogServices.search( [ ("cost_id", "in", [cost.id for cost in self.cost_ids ] )] )
        #VEHICLE COST that have comsumable products, 
        for service in services:
            if( service.cost_subtype_id.is_consumable and service.cost_subtype_id.product_id ) :
                product = service.cost_subtype_id.product_id
                if product_n_qty_list.get( product.id , False):
                    product_n_qty_list[ product.id ]['qty'] += service.product_uom_qty
                else : 
                    product_n_qty_list[ product.id ] = {
                        'product_id' : service.cost_subtype_id.product_id,
                        'qty' : service.product_uom_qty,
                    }
        #COP TAG COST That have consumable products
        for tag_log in self.tag_log_ids:
            if( tag_log.tag_id.is_consumable and tag_log.tag_id.product_id ) :
                product = tag_log.tag_id.product_id
                if product_n_qty_list.get( product.id , False):
                    product_n_qty_list[ product.id ]['qty'] += tag_log.product_uom_qty
                else : 
                    product_n_qty_list[ product.id ] = {
                        'product_id' : tag_log.tag_id.product_id,
                        'qty' : tag_log.product_uom_qty,
                    }

        move_lines = []
        move_lines_dict = {}
        for product_id, obj in product_n_qty_list.items():
            self._generate_moves( product_id, obj['qty'] )
            product= obj['product_id']
            journal_id, acc_src, acc_dest, acc_valuation = self._get_accounting_data_for_valuation( product )
            if move_lines_dict.get( acc_src , False):
                credit_value = self._prepare_credit_product_cost( product, obj['qty'], product.standard_price)
                move_lines_dict[ acc_src ][2]['credit'] += credit_value
            else : 
                credit_value = self._prepare_credit_product_cost( product, obj['qty'], product.standard_price)
                move_lines_dict[ acc_src ] = (0, 0, {
                    'name': self.name,
                    'ref': self.name,
                    'credit': credit_value if credit_value > 0 else 0,
                    'debit':  0,
                    'account_id': acc_src,
                })
        for acc, obj in move_lines_dict.items():
            move_lines += [obj]
        
        self._account_entry_move_ore( move_lines )
        self.tag_log_ids.post()
        self.cost_ids.post()
        self.rit_ids.post()
        self.hourmeter_ids.post()
        self.write({ 'state' : 'done' })
        
    
    def _generate_moves(self, product_id, qty):
        product = self.env['product.product'].search( [ ("id", "=", product_id ) ] )
        
        domain_quant = [ ("product_id", "=", product_id ), ("location_id.usage", "=", "internal" ) ]
        stock_quants = self.env['stock.quant'].read_group( domain_quant, [ 'location_id', 'product_id', 'qty'], ["location_id", 'product_id'], orderby='id')
        location_id = None
        for stock_quant in stock_quants:
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

    def _account_entry_move_ore(self, move_lines ):
        production_config = self.production_config_id
        if not production_config :
            raise UserError(_('Please Set Default Configuration file') )
        if not production_config.lot_id :
            raise UserError(_('Please Set Default Lot Product Configuration file') )

        journal_id, acc_src, acc_dest, acc_valuation = self._get_accounting_data_for_valuation( production_config.lot_id.product_id )
        AccountMove = self.env['account.move']
        debit_amount = 0
        for move_line in move_lines:
            debit_amount += move_line[2]["credit"]

        product = production_config.lot_id.product_id
        debit_line_vals = {
            'name': self.name,
            'product_id': product.id,
            'quantity': 0,
            'product_uom_id': product.uom_id.id,
            'ref': self.name,
            'partner_id': False,
            'debit': debit_amount,
            'credit':  0,
            'account_id': acc_valuation,
        }
        
        if move_lines:
            move_lines.append((0, 0, debit_line_vals))
            date = self._context.get('force_period_date', fields.Date.context_today(self))
            new_account_move = AccountMove.create({
                'journal_id': journal_id,
                'line_ids': move_lines,
                'date': date,
                'ref': self.name})
            new_account_move.post()

            product_qty = product.qty_available
            amount_unit = product.standard_price
            not_consumable_cost = self._compute_not_consumable_cost()
            new_std_price = (( amount_unit * product_qty ) + not_consumable_cost + debit_amount ) / ( product_qty )
            product.with_context(force_company=self.company_id.id).sudo().write({ 'standard_price': new_std_price })

    def _prepare_credit_product_cost(self, product, qty, cost):
        """
        Generate the account.move.line values to post to track the stock valuation difference due to the
        processing of the given quant.
        """
        self.ensure_one()
        valuation_amount = cost
        if self._context.get('force_valuation_amount'):
            valuation_amount = self._context.get('force_valuation_amount')
        else:
            if product.cost_method == 'average':
                valuation_amount = cost if product.cost_method == 'real' else product.standard_price
        credit_value = self.company_id.currency_id.round(valuation_amount * qty)
        return credit_value

    def _compute_not_consumable_cost(self):
        sum_rit = sum( [ rit.cost_amount for rit in self.rit_ids ] )
        sum_hm = sum( [ hourmeter.cost_amount for hourmeter in self.hourmeter_ids ] )
        # except VEHICLE COST and COP TAG COST that have comsumable products
        # because it already compute in stock move ( stock interim cost )
        sum_cop_tag = sum( [ tag_log.amount for tag_log in self.tag_log_ids if not ( tag_log.tag_id.is_consumable and tag_log.tag_id.product_id ) ] )
        sum_vehicle_cost = sum( [ cost.amount for cost in self.cost_ids if not ( cost.cost_subtype_id.is_consumable and cost.cost_subtype_id.product_id ) ] )
        return sum_hm + sum_rit + sum_cop_tag + sum_vehicle_cost

    @api.multi
    def _get_accounting_data_for_valuation(self, product_id):
        """ Return the accounts and journal to use to post Journal Entries for
        the real-time valuation of the quant. """
        self.ensure_one()
        accounts_data = product_id.product_tmpl_id.get_product_accounts()
        acc_src = accounts_data['stock_input'].id
        acc_dest = accounts_data['stock_output'].id
 
        acc_valuation = accounts_data.get('stock_valuation', False)
        if acc_valuation:
            acc_valuation = acc_valuation.id
        if not accounts_data.get('stock_journal', False):
            raise UserError(_('You don\'t have any stock journal defined on your product category, check if you have installed a chart of accounts'))
        if not acc_src:
            raise UserError(_('Cannot find a stock input account for the product %s. You must define one on the product category, or on the location, before processing this operation.') % (self.product_id.name))
        if not acc_dest:
            raise UserError(_('Cannot find a stock output account for the product %s. You must define one on the product category, or on the location, before processing this operation.') % (self.product_id.name))
        if not acc_valuation:
            raise UserError(_('You don\'t have any stock valuation account defined on your product category. You must define one before processing this operation.'))
        journal_id = accounts_data['stock_journal'].id
        return journal_id, acc_src, acc_dest, acc_valuation

    # def _account_entry_move_ore(self, move_lines ):
    #     production_config = self.production_config_id
    #     if not production_config :
    #         raise UserError(_('Please Set Default Configuration file') )
    #     if not production_config.lot_id :
    #         raise UserError(_('Please Set Default Lot Product Configuration file') )

    #     journal_id, acc_src, acc_dest, acc_valuation = self._get_accounting_data_for_valuation( production_config.lot_id.product_id )
    #     AccountMove = self.env['account.move']
    #     move_lines = [ move_line for move_line in move_lines if move_line[2]["debit"] > 0 ]
    #     debit_amount = 0
    #     for move_line in move_lines:
    #         move_line[2]["account_id"] = acc_dest
    #         move_line[2]["credit"] = move_line[2]["debit"]
    #         debit_amount += move_line[2]["debit"]
    #         move_line[2]["debit"] = 0
    #     product = production_config.lot_id.product_id
    #     debit_line_vals = {
    #         'name': self.name,
    #         'product_id': product.id,
    #         'quantity': 0,
    #         'product_uom_id': product.uom_id.id,
    #         'ref': self.name,
    #         'partner_id': False,
    #         'debit': debit_amount,
    #         'credit':  0,
    #         'account_id': acc_valuation,
    #     }
        
    #     if move_lines:
    #         move_lines.append((0, 0, debit_line_vals))
    #         _logger.warning( move_lines )
    #         date = self._context.get('force_period_date', fields.Date.context_today(self))
    #         new_account_move = AccountMove.create({
    #             'journal_id': journal_id,
    #             'line_ids': move_lines,
    #             'date': date,
    #             'ref': self.name})
    #         new_account_move.post()

    #         product_qty = product.qty_available
    #         amount_unit = product.standard_price
    #         amount_rit_hm = self.get_amount_rit_hm()
    #         new_std_price = (( amount_unit * product_qty ) + amount_rit_hm + debit_amount ) / ( product_qty )
    #         product.with_context(force_company=self.company_id.id).sudo().write({ 'standard_price': new_std_price })


    # create COP journal entry
    # def _account_entry_move(self, costs_subtype, qty):
    #     """ Accounting COP Entries """
    #     journal_id, acc_src, acc_dest, cop_account_id = costs_subtype._get_accounting_data_for_cop()
    #     production_config = self.production_config_id
    #     if not production_config :
    #         raise UserError(_('Please Set Default Configuration file') )
        
    #     journal_id = production_config.cop_journal_id.id if production_config.cop_journal_id else journal_id

    #     move_lines = self.with_context(force_company=self.company_id.id)._create_account_move_line(costs_subtype, qty , cop_account_id, acc_dest, journal_id)
    #     return move_lines

    #     # if self.company_id.anglo_saxon_accounting:
    #     #     # Creates an account entry from stock_input to stock_output on a dropship move. https://github.com/odoo/odoo/issues/12687
    #     #     journal_id, acc_src, acc_dest, acc_valuation = move._get_accounting_data_for_valuation()
    #     #     if move.location_id.usage == 'supplier' and move.location_dest_id.usage == 'customer':
    #     #         self.with_context(force_company=move.company_id.id)._create_account_move_line(move, acc_src, acc_dest, journal_id)
    #     #     if move.location_id.usage == 'customer' and move.location_dest_id.usage == 'supplier':
    #     #         self.with_context(force_company=move.company_id.id)._create_account_move_line(move, acc_dest, acc_src, journal_id)

    # def _create_account_move_line(self, costs_subtype, qty , credit_account_id, debit_account_id, journal_id):
       
    #     AccountMove = self.env['account.move']
    #     move_lines = self._prepare_account_move_line( costs_subtype.product_id, qty, costs_subtype.product_id.standard_price , credit_account_id, debit_account_id)
    #     if move_lines:
    #         date = self._context.get('force_period_date', fields.Date.context_today(self))
    #         new_account_move = AccountMove.create({
    #             'journal_id': journal_id,
    #             'line_ids': move_lines,
    #             'date': date,
    #             'ref': self.name})
    #         new_account_move.post()
    #     return move_lines

        
    # def _prepare_account_move_line(self, product, qty, cost, credit_account_id, debit_account_id):
    #     """
    #     Generate the account.move.line values to post to track the stock valuation difference due to the
    #     processing of the given quant.
    #     """
    #     self.ensure_one()
    #     valuation_amount = cost
    #     if self._context.get('force_valuation_amount'):
    #         valuation_amount = self._context.get('force_valuation_amount')
    #     else:
    #         if product.cost_method == 'average':
    #             valuation_amount = cost if product.cost_method == 'real' else product.standard_price
    #     # the standard_price of the product may be in another decimal precision, or not compatible with the coinage of
    #     # the company currency... so we need to use round() before creating the accounting entries.
    #     debit_value = self.company_id.currency_id.round(valuation_amount * qty)

    #     # check that all data is correct
    #     if self.company_id.currency_id.is_zero(debit_value):
    #         if product.cost_method == 'standard':
    #             raise UserError(_("The found valuation amount for product %s is zero. Which means there is probably a configuration error. Check the costing method and the standard price") % (product.name,))
    #         return []
    #     credit_value = debit_value
    #     partner_id = False #(self.picking_id.partner_id and self.env['res.partner']._find_accounting_partner(self.picking_id.partner_id).id) or False
    #     debit_line_vals = {
    #         'name': self.name,
    #         'product_id': product.id,
    #         'quantity': qty,
    #         'product_uom_id': product.uom_id.id,
    #         'ref': self.name,
    #         'partner_id': partner_id,
    #         'debit': debit_value if debit_value > 0 else 0,
    #         'credit': -debit_value if debit_value < 0 else 0,
    #         'account_id': debit_account_id,
    #     }
    #     credit_line_vals = {
    #         'name': self.name,
    #         'product_id': product.id,
    #         'quantity': qty,
    #         'product_uom_id': product.uom_id.id,
    #         'ref': self.name,
    #         'partner_id': partner_id,
    #         'credit': credit_value if credit_value > 0 else 0,
    #         'debit': -credit_value if credit_value < 0 else 0,
    #         'account_id': credit_account_id,
    #     }
    #     res = [(0, 0, debit_line_vals), (0, 0, credit_line_vals)]
    #     if credit_value != debit_value:
    #         # for supplier returns of product in average costing method, in anglo saxon mode
    #         diff_amount = debit_value - credit_value
    #         price_diff_account = product.property_account_creditor_price_difference
    #         if not price_diff_account:
    #             price_diff_account = product.categ_id.property_account_creditor_price_difference_categ
    #         if not price_diff_account:
    #             raise UserError(_('Configuration error. Please configure the price difference account on the product or its category to process this operation.'))
    #         price_diff_line = {
    #             'name': self.name,
    #             'product_id': product.id,
    #             'quantity': qty,
    #             'product_uom_id': product.uom_id.id,
    #             'ref': self.name,
    #             'partner_id': partner_id,
    #             'credit': diff_amount > 0 and diff_amount or 0,
    #             'debit': diff_amount < 0 and -diff_amount or 0,
    #             'account_id': price_diff_account.id,
    #         }
    #         res.append((0, 0, price_diff_line))
    #     return res