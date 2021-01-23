# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time
from odoo.addons import decimal_precision as dp
import logging
_logger = logging.getLogger(__name__)

class ProductionCopAdjust(models.Model):
    _name = "production.cop.adjust"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = "id desc"

    @api.model
    def _default_config(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0]
    
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
    date = fields.Date('Date', help='', default=fields.Datetime.now, states=READONLY_STATES )
    end_date = fields.Date('Date', help='', default=fields.Datetime.now, states=READONLY_STATES )
    employee_id	= fields.Many2one('hr.employee', string='Responsible', states=READONLY_STATES )
    production_config_id	= fields.Many2one('production.config', string='Production Config', default=_default_config, states=READONLY_STATES )
    cost_ids = fields.One2many('fleet.vehicle.cost', 'cop_adjust_id', 'Vehicle Costs', states=READONLY_STATES )
    rit_ids = fields.One2many('production.ritase.counter', 'cop_adjust_id', 'Ritase Costs', states=READONLY_STATES )
    hourmeter_ids = fields.One2many('production.vehicle.hourmeter.log', 'cop_adjust_id', 'Hourmeter Costs', states=READONLY_STATES )
    watertruck_ids = fields.One2many('production.watertruck.counter', 'cop_adjust_id', 'Water Truck Costs', states=READONLY_STATES )

    tag_log_ids = fields.One2many('production.cop.tag.log', 'cop_adjust_id', 'COP Tagging', states=READONLY_STATES )
    vehicle_losstime_ids = fields.One2many('fleet.vehicle.losstime', 'cop_adjust_id', 'Vehicle Losstime', states=READONLY_STATES )
    losstime_accumulation_ids = fields.One2many('production.losstime.accumulation', 'cop_adjust_id', 'Losstime Accumulation', states=READONLY_STATES )
    amount = fields.Float(string='Amount', compute="_compute_amount" )

    sum_rit = fields.Float(string='Ritase Amount', compute="_compute_amount" )
    sum_hm = fields.Float(string='Hourmeter Amount', compute="_compute_amount" )
    sum_watertruck = fields.Float(string='Water Truck Amount', compute="_compute_amount" )
    sum_losstime_accumulation = fields.Float(string='Lostime Amount', compute="_compute_amount" )
    sum_vehicle_cost = fields.Float(string='Vehicle Cost Amount', compute="_compute_amount" )

    production_order_ids = fields.Many2many('production.order', 'production_cop_adjust_production_order_rel', 'cop_adjust_id', 'production_order_id', 'Production Order', copy=False, states=READONLY_STATES)
    produced_items = fields.One2many('production.product', 'cop_adjust_id', 'Produced Item', states=READONLY_STATES )

    state = fields.Selection( [
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
        self._settle_cost()

    @api.multi
    def action_confirm(self):
        self.ensure_one()
        self.write({ 'state' : 'confirm' })

    @api.multi
    def action_reload(self):
        for record in self:
            if record.state == 'done':
                continue
            record._reload()
    
    @api.multi
    def action_cancel(self):
        self.ensure_one()
        if any( self.tag_log_ids.filtered(lambda r: r.state == 'posted') ) :
            raise UserError(_('Unable to cancel order %s as some receptions have already been done.') % (self.name))
        self.write({ 'state' : 'cancel' })

    @api.multi
    def action_draft(self):
        self.ensure_one()
        if any( self.tag_log_ids.filtered(lambda r: r.state == 'posted') ) :
            raise UserError(_('Unable to cancel order %s as some receptions have already been done.') % (self.name))
        self.write({ 'state' : 'draft' })
    
    @api.multi
    def _reload(self):
        self.ensure_one()
        VehicleCost = self.env['fleet.vehicle.cost'].sudo()
        vehicle_costs = VehicleCost.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ), ( "state", "=", "draft" ) ] )
        vehicle_costs_ids = [ vehicle_cost.id for vehicle_cost in vehicle_costs if vehicle_cost.cost_subtype_id.is_consumable ]
        self.update({
            'cost_ids': [( 6, 0, vehicle_costs_ids )],
        })

        RitaseCounter = self.env['production.ritase.counter'].sudo()
        ritase_counter = RitaseCounter.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ), ( "state", "=", "draft" ), ( "ritase_order_id.state", "=", "done" ) ] )
        # ritase_counter = RitaseCounter.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ), ( "state", "=", "draft" ) ] )
        self.update({
            'rit_ids': [( 6, 0, ritase_counter.ids )],
        })

        HourmeterLog = self.env['production.vehicle.hourmeter.log'].sudo()
        hourmeter_log = HourmeterLog.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ), ( "state", "=", "draft" ), ( "hourmeter_order_id.state", "=", "done" ) ] )
        # hourmeter_log = HourmeterLog.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ), ( "state", "=", "draft" ) ] )
        self.update({
            'hourmeter_ids': [( 6, 0, hourmeter_log.ids )],
        })

        WaterTruck = self.env['production.watertruck.counter'].sudo()
        watertrucks = WaterTruck.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ), ( "state", "=", "draft" ), ( "order_id.state", "=", "done" ) ] )
        # watertrucks = WaterTruck.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ) , ( "state", "=", "draft" ) ] )
        self.update({
            'watertruck_ids': [( 6, 0, watertrucks.ids )],
        })

        CopTagLog = self.env['production.cop.tag.log'].sudo()
        tag_log = CopTagLog.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ), ( "state", "=", "draft" ) ] )
        self.update({
            'tag_log_ids': [( 6, 0, tag_log.ids )],
        })

        VehicleLosstime = self.env['fleet.vehicle.losstime'].sudo()
        vehicle_losstime = VehicleLosstime.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ), ( "state", "=", "draft" ) ] )
        self.update({
            'vehicle_losstime_ids': [( 6, 0, vehicle_losstime.ids )],
        })

        self.adjust_losstime()
        self.get_produced_item()
        return True
    
    def get_produced_item(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        product_ids = [ x.id for x in production_config[0].product_ids ]
        _logger.warning( product_ids )
        product_ids = self.env['product.product'].sudo(  ).search( [ ("id", "in", product_ids ) ] )

        ProductionOrder = self.env['production.order'].sudo()
        production_orders = ProductionOrder.search( [ ( "date", ">=", self.date ), ( "date", "<=", self.end_date ) ] )
        product_qty_dict = {}
        for production_order in production_orders :
            if product_qty_dict.get( production_order.product_id.id , False):
                product_qty_dict[ production_order.product_id.id ] += production_order.product_qty
            else:
                product_qty_dict[ production_order.product_id.id ] = production_order.product_qty

        self.produced_items.unlink()
        for product, qty in product_qty_dict.items():
            self.env['production.product'].sudo().create({
                'cop_adjust_id' : self.id,
                'product_id' : product,
                'product_qty' : qty,
            })

    def adjust_losstime(self):
        self.ensure_one()
        self.losstime_accumulation_ids.unlink()
        vehicle_driver_date_dict = {}
        for vehicle_losstime_id in self.vehicle_losstime_ids:
            if vehicle_losstime_id.losstime_type not in ("slippery", "rainy"):
                continue
            vehicle_id = vehicle_losstime_id.vehicle_id.id
            driver_id = vehicle_losstime_id.driver_id.id
            minimal_cash = 0
            tag_id = False
            # RIT
            if self.production_config_id.rit_vehicle_tag_id.id in vehicle_losstime_id.tag_ids.ids :
                minimal_cash = self.production_config_id.rit_minimal_cash
                tag_id = self.production_config_id.rit_losstime_tag_id.id
            # HM
            if self.production_config_id.hm_vehicle_tag_id.id in vehicle_losstime_id.tag_ids.ids :
                minimal_cash = self.production_config_id.hm_minimal_cash
                tag_id = self.production_config_id.hm_losstime_tag_id.id
            # WT
            if self.production_config_id.wt_vehicle_tag_id.id in vehicle_losstime_id.tag_ids.ids :
                minimal_cash = self.production_config_id.wt_minimal_cash
                tag_id = self.production_config_id.wt_losstime_tag_id.id

            temp = {
                'date' : vehicle_losstime_id.date,
                'losstime_type' : vehicle_losstime_id.losstime_type,
                'tag_id' : tag_id,
                'reference' : '',
                'amount' : minimal_cash
            }
            if vehicle_driver_date_dict.get( vehicle_id , False):
                if vehicle_driver_date_dict[ vehicle_id ].get( driver_id , False):
                    if vehicle_driver_date_dict[ vehicle_id ][ driver_id ].get( temp['date'] , False):
                        vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ temp['date'] ] = temp
                    else :
                        vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ temp['date'] ] = temp
                else :
                    vehicle_driver_date_dict[ vehicle_id ][ driver_id ] = {}
                    vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ temp['date'] ] = temp
            else :
                vehicle_driver_date_dict[ vehicle_id ] = {}
                vehicle_driver_date_dict[ vehicle_id ][ driver_id ] = {}
                vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ temp['date'] ] = temp
        
        for rit_id in self.rit_ids:
            vehicle_id = rit_id.vehicle_id.id
            driver_id = rit_id.driver_id.id
            if vehicle_driver_date_dict.get( vehicle_id , False):
                if vehicle_driver_date_dict[ vehicle_id ].get( driver_id , False):
                    if vehicle_driver_date_dict[ vehicle_id ][ driver_id ].get( rit_id.date , False):
                        if vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ rit_id.date ]['amount'] - rit_id.amount >= 0 :
                            vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ rit_id.date ]['amount'] -= rit_id.amount
                        else :
                            vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ rit_id.date ]['amount'] = 0
                        vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ rit_id.date ]['reference'] += ','+rit_id.ritase_order_id.name
        
        for hourmeter_id in self.hourmeter_ids:
            vehicle_id = hourmeter_id.vehicle_id.id
            driver_id = hourmeter_id.driver_id.id
            if vehicle_driver_date_dict.get( vehicle_id , False):
                if vehicle_driver_date_dict[ vehicle_id ].get( driver_id , False):
                    if vehicle_driver_date_dict[ vehicle_id ][ driver_id ].get( hourmeter_id.date , False):
                        if vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ hourmeter_id.date ]['amount'] - hourmeter_id.amount >= 0 :
                            vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ hourmeter_id.date ]['amount'] -= hourmeter_id.amount
                        else :
                            vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ hourmeter_id.date ]['amount'] = 0
                        vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ hourmeter_id.date ]['reference'] += ','+hourmeter_id.hourmeter_order_id.name

        for watertruck_id in self.watertruck_ids:
            vehicle_id = watertruck_id.vehicle_id.id
            driver_id = watertruck_id.driver_id.id
            if vehicle_driver_date_dict.get( vehicle_id , False):
                if vehicle_driver_date_dict[ vehicle_id ].get( driver_id , False):
                    if vehicle_driver_date_dict[ vehicle_id ][ driver_id ].get( watertruck_id.date , False):
                        if vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ watertruck_id.date ]['amount'] - watertruck_id.amount >= 0 :
                            vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ watertruck_id.date ]['amount'] -= watertruck_id.amount
                        else :
                            vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ watertruck_id.date ]['amount'] = 0
                        vehicle_driver_date_dict[ vehicle_id ][ driver_id ][ watertruck_id.date ]['reference'] += ','+watertruck_id.order_id.name

        LosstimeAccumulation = self.env['production.losstime.accumulation'].sudo()
        for vehicle_id, driver in vehicle_driver_date_dict.items():
            for driver_id, date_obj in driver.items():
                for date , obj in date_obj.items():
                    LosstimeAccumulation.create({
                        'cop_adjust_id' : self.id,
                        'date' : obj['date'],
                        'tag_id' : obj['tag_id'],
                        'vehicle_id' : vehicle_id,
                        'driver_id' : driver_id,
                        'losstime_type' : obj['losstime_type'],
                        'reference' : obj['reference'],
                        'amount' : obj['amount'],
                    })
        return


    @api.depends("rit_ids", "hourmeter_ids", "watertruck_ids", "cost_ids", "tag_log_ids" )
    def _compute_amount(self):
        for record in self:
            record.sum_rit = sum( [ rit.amount for rit in record.rit_ids ] )
            record.sum_hm = sum( [ hourmeter.amount for hourmeter in record.hourmeter_ids ] )
            record.sum_watertruck = sum( [ watertruck.amount for watertruck in record.watertruck_ids ] )

            record.sum_losstime_accumulation = sum( [ losstime_accumulation_id.amount for losstime_accumulation_id in record.losstime_accumulation_ids ] )
            record.sum_vehicle_cost = sum( [ cost.amount for cost in record.cost_ids ] )

            if record.state != 'done' :
                sum_rit = sum( [ rit.amount for rit in record.rit_ids.filtered(lambda r: r.state != 'posted') ] )
                sum_hm = sum( [ hourmeter.amount for hourmeter in record.hourmeter_ids.filtered(lambda r: r.state != 'posted') ] )
                sum_watertruck = sum( [ watertruck.amount for watertruck in record.watertruck_ids.filtered(lambda r: r.state != 'posted') ] )

                sum_losstime_accumulation = sum( [ losstime_accumulation_id.amount for losstime_accumulation_id in record.losstime_accumulation_ids.filtered(lambda r: r.state != 'posted') ] )
                sum_vehicle_cost = sum( [ cost.amount for cost in record.cost_ids.filtered(lambda r: r.state != 'posted') ] )
                sum_cop_tag = sum( [ tag_log.amount for tag_log in record.tag_log_ids.filtered(lambda r: r.state != 'posted') ] )
                record.amount = sum_hm + sum_rit + sum_watertruck + sum_cop_tag + sum_vehicle_cost + sum_losstime_accumulation
            else:
                sum_cop_tag = sum( [ tag_log.amount for tag_log in record.tag_log_ids.filtered(lambda r: r.state == 'posted') ] )
                record.amount = sum_cop_tag

    @api.multi
    def _settle_cost(self):
        self.ensure_one()
        product_n_qty_list = {}
        #VEHICLE COST that have stockable products, 
        for cost_id in self.cost_ids:
            if( cost_id.cost_subtype_id.is_consumable and cost_id.cost_subtype_id.product_id ) :
                product = cost_id.cost_subtype_id.product_id
                if product_n_qty_list.get( product.id , False):
                    product_n_qty_list[ product.id ]['qty'] += cost_id.product_uom_qty
                else : 
                    product_n_qty_list[ product.id ] = {
                        'product_id' : cost_id.cost_subtype_id.product_id,
                        'qty' : cost_id.product_uom_qty,
                    }
        #COP TAG LOG That have stockable products
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
        self.watertruck_ids.post()
        self.vehicle_losstime_ids.post()
        self.losstime_accumulation_ids.post()
        self.write({ 'state' : 'done' })
        
    
    def _generate_moves(self, product_id, qty):
        self.ensure_one()
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
        self.ensure_one()
        production_config = self.production_config_id
        if not production_config :
            raise UserError(_('Please Set Default Configuration file') )
        if not production_config.lot_id :
            raise UserError(_('Please Set Default Lot Product Configuration file') )
        if not production_config.cop_cost_credit_account_id :
            raise UserError(_('Please Set COP Cost Credit Account in Configuration file') )

        journal_id, acc_src, acc_dest, acc_valuation = self._get_accounting_data_for_valuation( production_config.lot_id.product_id )
        AccountMove = self.env['account.move'].sudo()
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
        # product_qty += self.get_qty_by_rit_product( except_prduct_id=product.id )
        # avoid division by zero
        if product_qty > 0 :
            amount_unit = product.standard_price
            not_consumable_cost = self._compute_not_consumable_cost()
            new_std_price = (( amount_unit * product_qty ) + not_consumable_cost + debit_amount ) / ( product_qty + self.get_qty_by_rit_product( except_prduct_id=product.id ) )
            product.with_context(force_company=self.company_id.id).sudo().write({ 'standard_price': new_std_price })
            #TODO : adjust stock ore account value with inventory value
            inventory_value = product.standard_price * product_qty
            tables = 'account_move_line'
            # compute the balance, debit and credit for the provided accounts
            request = ("SELECT account_id AS id, SUM(debit) AS debit, SUM(credit) AS credit, (SUM(debit) - SUM(credit)) AS balance" +\
                    " FROM " + tables + " WHERE account_id = " + str(acc_valuation) + " GROUP BY account_id")
            self.env.cr.execute(request)
            balance = 0
            for row in self.env.cr.dictfetchall():
                balance += row['balance']
            diff =  inventory_value - balance

            if diff != 0 :
                move_lines = []
                credit_account_id = production_config.cop_cost_credit_account_id.id
                move_lines += [(0, 0, {
                        'name': self.name,
                        'ref': self.name,
                        'credit': abs(diff) if diff > 0 else 0,
                        'debit':  abs(diff) if diff < 0 else 0,
                        'account_id': credit_account_id,
                    })]
                move_lines += [(0, 0, {
                        'name': self.name,
                        'product_id': product.id,
                        'quantity': 0,
                        'product_uom_id': product.uom_id.id,
                        'ref': self.name,
                        'partner_id': False,
                        'credit': abs(diff) if diff < 0 else 0,
                        'debit':  abs(diff) if diff > 0 else 0,
                        'account_id': acc_valuation,
                    })]
                date = self._context.get('force_period_date', fields.Date.context_today(self))
                new_account_move = AccountMove.create({
                    'journal_id': journal_id,
                    'line_ids': move_lines,
                    'date': date,
                    'ref': self.name})
                new_account_move.post()

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

    def get_qty_by_rit_product( self, except_prduct_id ):
        self.ensure_one()
        product_dict = {}
        qty = 0
        for rit in self.rit_ids:
            product = rit.ritase_order_id.product_id
            # _logger.warning( product )
            # _logger.warning( product.qty_available )
            if except_prduct_id == product.id :
                continue
            if product_dict.get( product.id , False):
                continue
                    # product_dict[ product.id ]['qty'] = product.qty_available
            else : 
                product_dict[ product.id ] = product.qty_available
                #  {
                #     'qty' : product.qty_available,
                # }
                # _logger.warning( product.qty_available )
                qty += product.qty_available
        return qty
            
    def _compute_not_consumable_cost(self):
        sum_rit = sum( [ rit.amount for rit in self.rit_ids ] )
        sum_hm = sum( [ hourmeter.amount for hourmeter in self.hourmeter_ids ] )
        sum_watertruck = sum( [ watertruck.amount for watertruck in self.watertruck_ids ] )

        sum_losstime_accumulation = sum( [ losstime_accumulation_id.amount for losstime_accumulation_id in self.losstime_accumulation_ids ] )
        # except VEHICLE COST and COP TAG COST that have comsumable products
        # because it already compute in stock move ( stock interim cost )
        sum_cop_tag = sum( [ tag_log.amount for tag_log in self.tag_log_ids if not ( tag_log.tag_id.is_consumable and tag_log.tag_id.product_id ) ] )
        sum_vehicle_cost = sum( [ cost.amount for cost in self.cost_ids if not ( cost.cost_subtype_id.is_consumable and cost.cost_subtype_id.product_id ) ] )

        return sum_hm + sum_rit + sum_watertruck + sum_cop_tag + sum_vehicle_cost + sum_losstime_accumulation

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

class ProductProduction(models.Model):
    _name = "production.product"

    cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP' )
    product_id = fields.Many2one(
        'product.product', 'Product',
        domain=[('type', 'in', ['product', 'consu'])],
        readonly=True )

    product_qty = fields.Float(
        'Quantity (WMT)',
        default=0.0, digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, required=True, store=True )