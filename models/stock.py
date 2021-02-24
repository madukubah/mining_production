# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from odoo import api, exceptions, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round
from odoo.addons import decimal_precision as dp

import logging
_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ritase_order_id = fields.Many2one("production.ritase.order", related='move_lines.ritase_order_id',
        string="Ritase", readonly=True)

class StockMoveLots(models.Model):
    _name = 'mining.stock.move.lots'
    _description = "Quantities to Process by lots"

    move_id = fields.Many2one('stock.move', 'Move')
    production_order_id = fields.Many2one('production.order', 'Production Order')
    lot_id = fields.Many2one(
        'stock.production.lot', 'Lot',
        domain="[('product_id', '=', product_id)]")
    lot_produced_id = fields.Many2one('stock.production.lot', 'Finished Lot')
    lot_produced_qty = fields.Float(
        'Quantity Finished Product', digits=dp.get_precision('Product Unit of Measure'),
        help="Informative, not used in matching")
    quantity = fields.Float('To Do', default=1.0, digits=dp.get_precision('Product Unit of Measure'))
    quantity_done = fields.Float('Done', digits=dp.get_precision('Product Unit of Measure'))
    product_id = fields.Many2one(
        'product.product', 'Product',
        readonly=True, related="move_id.product_id", store=True)
    done_wo = fields.Boolean('Done for Work Order', default=True, help="Technical Field which is False when temporarily filled in in work order")  # TDE FIXME: naming
    done_move = fields.Boolean('Move Done', related='move_id.is_done', store=True)  # TDE FIXME: naming
    plus_visible = fields.Boolean("Plus Visible", compute='_compute_plus')

    @api.one
    @api.constrains('lot_id', 'quantity_done')
    def _check_lot_id(self):
        if self.move_id.product_id.tracking == 'serial':
            lots = set([])
            for move_lot in self.move_id.active_move_lot_ids.filtered(lambda r: not r.lot_produced_id and r.lot_id):
                if move_lot.lot_id in lots:
                    raise exceptions.UserError(_('You cannot use the same serial number in two different lines.'))
                if float_compare(move_lot.quantity_done, 1.0, precision_rounding=move_lot.product_id.uom_id.rounding) == 1:
                    raise exceptions.UserError(_('You can only produce 1.0 %s for products with unique serial number.') % move_lot.product_id.uom_id.name)
                lots.add(move_lot.lot_id)

    def _compute_plus(self):
        for movelot in self:
            if movelot.move_id.product_id.tracking == 'serial':
                movelot.plus_visible = (movelot.quantity_done <= 0.0)
            else:
                movelot.plus_visible = (movelot.quantity == 0.0) or (movelot.quantity_done < movelot.quantity)

    @api.multi
    def do_plus(self):
        self.ensure_one()
        self.quantity_done = self.quantity_done + 1
        return self.move_id.split_move_lot()

    @api.multi
    def do_minus(self):
        self.ensure_one()
        self.quantity_done = self.quantity_done - 1
        return self.move_id.split_move_lot()

    @api.multi
    def write(self, vals):
        if 'lot_id' in vals:
            for movelot in self:
                movelot.move_id.production_order_id.move_ids.mapped('move_lot_ids')\
                    .filtered(lambda r: r.done_wo and not r.done_move and r.lot_produced_id == movelot.lot_id)\
                    .write({'lot_produced_id': vals['lot_id']})
        return super(StockMoveLots, self).write(vals)

class StockMove(models.Model):
    _inherit = 'stock.move'

    ritase_order_id = fields.Many2one("production.ritase.order",
        'Ritase', ondelete='set null', index=True, readonly=True)
    production_order_id = fields.Many2one("production.order",
        'Production Order', ondelete='set null')
    
    has_tracking = fields.Selection(related='product_id.tracking', string='Product with Tracking')  # TDE FIXME: naming ...
    # Quantities to process, in normalized UoMs
    quantity_available = fields.Float(
        'Quantity Available', compute="_qty_available",
        digits=dp.get_precision('Product Unit of Measure'))
    quantity_done_store = fields.Float('Quantity done store', digits=0)
    quantity_done = fields.Float(
        'Quantity', compute='_qty_done_compute', inverse='_qty_done_set',
        digits=dp.get_precision('Product Unit of Measure'))
    move_lot_ids = fields.One2many('mining.stock.move.lots', 'move_id', string='Lots')
    active_move_lot_ids = fields.One2many('mining.stock.move.lots', 'move_id', domain=[('done_wo', '=', True)], string='Lots')
    unit_factor = fields.Float('Unit Factor')
    is_done = fields.Boolean(
        'Done', compute='_compute_is_done',
        store=True,
        help='Technical Field to order moves')  # TDE: what ?

    @api.depends('state', 'product_uom_qty', 'reserved_availability')
    def _qty_available(self):
        for move in self:
            # For consumables, state is available so availability = qty to do
            if move.state == 'assigned':
                move.quantity_available = move.product_uom_qty
            elif move.product_id.uom_id and move.product_uom:
                move.quantity_available = move.product_id.uom_id._compute_quantity(move.reserved_availability, move.product_uom)

    @api.multi
    @api.depends('move_lot_ids', 'move_lot_ids.quantity_done', 'quantity_done_store')
    def _qty_done_compute(self):
        for move in self:
            if move.has_tracking != 'none' or move.sudo().move_lot_ids.mapped('lot_id'):
                move.quantity_done = sum(move.move_lot_ids.filtered(lambda x: x.done_wo).mapped('quantity_done')) #TODO: change with active_move_lot_ids?
            else:
                move.quantity_done = move.quantity_done_store

    @api.multi
    def _qty_done_set(self):
        for move in self:
            if move.has_tracking == 'none':
                move.quantity_done_store = move.quantity_done

    @api.multi
    @api.depends('state')
    def _compute_is_done(self):
        for move in self:
            move.is_done = (move.state in ('done', 'cancel'))

    @api.multi
    def action_assign(self, no_prepare=False):
        res = super(StockMove, self).action_assign(no_prepare=no_prepare)
        self.check_move_lots()
        return res

    def _propagate_cancel(self):
        self.ensure_one()
        if not self.move_dest_id.production_order_id:
            super(StockMove, self)._propagate_cancel()
        elif self.move_dest_id.state == 'waiting':
            # If waiting, the chain will be broken and we are not sure if we can still wait for it (=> could take from stock instead)
            self.move_dest_id.write({'state': 'confirmed'})

    @api.multi
    def action_cancel(self):
        # for move in self:
        #     _logger.warning( move.quantity_done )
        if any(move.quantity_done for move in self):
            raise exceptions.UserError(_('You cannot cancel a move move having already consumed material'))
        return super(StockMove, self).action_cancel()

    @api.multi
    def check_move_lots(self):
        moves_todo = self.filtered(lambda x: x.production_order_id and x.state not in ('done', 'cancel'))
        return moves_todo.create_lots()

    @api.multi
    def create_lots(self):
        lots = self.env['mining.stock.move.lots']
        for move in self:
            unlink_move_lots = move.move_lot_ids.filtered(lambda x : (x.quantity_done == 0) and x.done_wo)
            unlink_move_lots.sudo().unlink()
            group_new_quant = {}
            old_move_lot = {}
            for movelot in move.move_lot_ids:
                key = (movelot.lot_id.id or False)
                old_move_lot.setdefault(key, []).append(movelot)
            for quant in move.reserved_quant_ids:
                key = (quant.lot_id.id or False)
                quantity = move.product_id.uom_id._compute_quantity(quant.qty, move.product_uom)
                if group_new_quant.get(key):
                    group_new_quant[key] += quantity
                else:
                    group_new_quant[key] = quantity
            for key in group_new_quant:
                quantity = group_new_quant[key]
                if old_move_lot.get(key):
                    if old_move_lot[key][0].quantity == quantity:
                        continue
                    else:
                        old_move_lot[key][0].quantity = quantity
                else:
                    vals = {
                        'move_id': move.id,
                        'product_id': move.product_id.id,
                        'production_order_id': move.production_order_id.id,
                        'quantity': quantity,
                        'lot_id': key,
                    }
                    lots.create(vals)
        return True

    @api.multi
    def _create_extra_move(self):
        ''' Creates an extra move if necessary depending on extra quantities than foreseen or extra moves'''
        self.ensure_one()
        quantity_to_split = 0
        uom_qty_to_split = 0
        extra_move = self.env['stock.move']
        rounding = self.product_uom.rounding
        link_procurement = False
        # If more produced than the procurement linked, you should create an extra move
        if self.procurement_id and self.production_order_id and float_compare(self.production_order_id.qty_produced, self.procurement_id.product_qty, precision_rounding=rounding) > 0:
            done_moves_total = sum(self.production_order_id.move_finished_ids.filtered(lambda x: x.product_id == self.product_id and x.state == 'done').mapped('product_uom_qty'))
            # If you depassed the quantity before, you don't need to split anymore, but adapt the quantities
            if float_compare(done_moves_total, self.procurement_id.product_qty, precision_rounding=rounding) >= 0:
                quantity_to_split = 0
                if float_compare( self.product_uom_qty, self.quantity_done, precision_rounding=rounding) < 0:
                    self.product_uom_qty = self.quantity_done #TODO: could change qty on move_dest_id also (in case of 2-step in/out)
            else:
                quantity_to_split = done_moves_total + self.quantity_done - self.procurement_id.product_qty
                uom_qty_to_split = self.product_uom_qty - (self.quantity_done - quantity_to_split)#self.product_uom_qty - (self.procurement_id.product_qty + done_moves_total)
                if float_compare(uom_qty_to_split, quantity_to_split, precision_rounding=rounding) < 0:
                    uom_qty_to_split = quantity_to_split
                self.product_uom_qty = self.quantity_done - quantity_to_split
        # You split also simply  when the quantity done is bigger than foreseen
        elif float_compare(self.quantity_done, self.product_uom_qty, precision_rounding=rounding) > 0:
            quantity_to_split = self.quantity_done - self.product_uom_qty
            uom_qty_to_split = quantity_to_split # + no need to change existing self.product_uom_qty 
            link_procurement = True
        if quantity_to_split:
            extra_move = self.copy(default={'quantity_done': quantity_to_split, 'product_uom_qty': uom_qty_to_split, 'production_order_id': self.production_order_id.id, 
                                            'production_order_id': self.production_order_id.id, 
                                            'procurement_id': link_procurement and self.procurement_id.id or False})
            extra_move.action_confirm()
            if self.has_tracking != 'none':
                qty_todo = self.quantity_done - quantity_to_split
                for movelot in self.move_lot_ids.filtered(lambda x: x.done_wo):
                    if movelot.quantity_done and movelot.done_wo:
                        if float_compare(qty_todo, movelot.quantity_done, precision_rounding=rounding) >= 0:
                            qty_todo -= movelot.quantity_done
                        elif float_compare(qty_todo, 0, precision_rounding=rounding) > 0:
                            #split
                            remaining = movelot.quantity_done - qty_todo
                            movelot.quantity_done = qty_todo
                            movelot.copy(default={'move_id': extra_move.id, 'quantity_done': remaining})
                            qty_todo = 0
                        else:
                            movelot.move_id = extra_move.id
            else:
                self.quantity_done -= quantity_to_split
        return extra_move

    @api.multi
    def move_validate(self):
        ''' Validate moves based on a production order. '''
        moves = self._filter_closed_moves()
        quant_obj = self.env['stock.quant']
        moves_todo = self.env['stock.move']
        moves_to_unreserve = self.env['stock.move']
        # Create extra moves where necessary
        for move in moves:
            # Here, the `quantity_done` was already rounded to the product UOM by the `do_produce` wizard. However,
            # it is possible that the user changed the value before posting the inventory by a value that should be
            # rounded according to the move's UOM. In this specific case, we chose to round up the value, because it
            # is what is expected by the user (if i consumed/produced a little more, the whole UOM unit should be
            # consumed/produced and the moves are split correctly).
            rounding = move.product_uom.rounding
            move.quantity_done = float_round(move.quantity_done, precision_rounding=rounding, rounding_method ='UP')
            if move.quantity_done <= 0:
                continue
            moves_todo |= move
            moves_todo |= move._create_extra_move()
        # Split moves where necessary and move quants
        for move in moves_todo:
            rounding = move.product_uom.rounding
            if float_compare(move.quantity_done, move.product_uom_qty, precision_rounding=rounding) < 0:
                # Need to do some kind of conversion here
                qty_split = move.product_uom._compute_quantity(move.product_uom_qty - move.quantity_done, move.product_id.uom_id)
                new_move = move.split(qty_split)
                # If you were already putting stock.move.lots on the next one in the work order, transfer those to the new move
                move.move_lot_ids.filtered(lambda x: not x.done_wo or x.quantity_done == 0.0).write({'move_id': new_move})
                self.browse(new_move).quantity_done = 0.0
            main_domain = [('qty', '>', 0)]
            preferred_domain = [('reservation_id', '=', move.id)]
            fallback_domain = [('reservation_id', '=', False)]
            fallback_domain2 = ['&', ('reservation_id', '!=', move.id), ('reservation_id', '!=', False)]
            preferred_domain_list = [preferred_domain] + [fallback_domain] + [fallback_domain2]
            if move.has_tracking == 'none':
                quants = quant_obj.quants_get_preferred_domain(move.product_qty, move, domain=main_domain, preferred_domain_list=preferred_domain_list)
                self.env['stock.quant'].quants_move(quants, move, move.location_dest_id, owner_id=move.restrict_partner_id.id)
            else:
                for movelot in move.active_move_lot_ids:
                    if float_compare(movelot.quantity_done, 0, precision_rounding=rounding) > 0:
                        if not movelot.lot_id:
                            raise UserError(_('You need to supply a lot/serial number.'))
                        qty = move.product_uom._compute_quantity(movelot.quantity_done, move.product_id.uom_id)
                        quants = quant_obj.quants_get_preferred_domain(qty, move, lot_id=movelot.lot_id.id, domain=main_domain, preferred_domain_list=preferred_domain_list)
                        self.env['stock.quant'].quants_move(quants, move, move.location_dest_id, lot_id = movelot.lot_id.id, owner_id=move.restrict_partner_id.id)
            moves_to_unreserve |= move
            # Next move in production order
            if move.move_dest_id and move.move_dest_id.state not in ('done', 'cancel'):
                move.move_dest_id.action_assign()
        moves_to_unreserve.quants_unreserve()
        moves_todo.write({'state': 'done', 'date': fields.Datetime.now()})
        return moves_todo

    @api.multi
    def action_done(self):
        production_moves = self.filtered(lambda move: (move.production_order_id) and not move.scrapped)
        production_moves.move_validate()
        return super(StockMove, self-production_moves).action_done()

    @api.multi
    def mining_split_move_lot(self):
        ctx = dict(self.env.context)
        self.ensure_one()
        view = self.env.ref('mining_production.view_mining_stock_move_lots')
        serial = (self.has_tracking == 'serial')
        only_create = False  # Check picking type in theory
        show_reserved = any([x for x in self.move_lot_ids if x.quantity > 0.0])
        ctx.update({
            'serial': serial,
            'only_create': only_create,
            'create_lots': True,
            'state_done': self.is_done,
            'show_reserved': show_reserved,
        })
        result = {
            'name': _('Register Lots'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'stock.move',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': self.id,
            'context': ctx,
        }
        return result

    @api.multi
    def save(self):
        return True

    def _propagate_split(self, new_move, qty):
        if not self.move_dest_id.production_order_id:
            super(StockMove, self)._propagate_split(new_move, qty)

    def _generate_move_phantom(self, bom_line, quantity):
        if bom_line.product_id.type in ['product', 'consu']:
            return self.copy(default={
                'picking_id': self.picking_id.id if self.picking_id else False,
                'product_id': bom_line.product_id.id,
                'product_uom': bom_line.product_uom_id.id,
                'product_uom_qty': quantity,
                'state': 'draft',  # will be confirmed below
                'name': self.name,
                'procurement_id': self.procurement_id.id,
                'split_from': self.id,  # Needed in order to keep sale connection, but will be removed by unlink
            })
        return self.env['stock.move']

class StockQuant(models.Model):
    _inherit = "stock.quant"

    @api.multi
    def _price_update(self, newprice):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Default Configuration file') )
        if not production_config.lot_id :
            raise UserError(_('Please Set Default Lot Product Configuration file') )
        if not production_config.cop_journal_id :
            raise UserError(_('Please Set Default COP Journal Configuration file') )
        
        product = production_config.lot_id.product_id
        for quant in self:
            if product.product_tmpl_id == quant.product_id.product_tmpl_id and quant.location_id.usage != "customer" :
                return
        super(StockQuant, self)._price_update(newprice)

    def _account_entry_move(self, move):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Default Configuration file') )
        if not production_config.lot_id :
            raise UserError(_('Please Set Default Lot Product Configuration file') )
        if not production_config.cop_journal_id :
            raise UserError(_('Please Set Default COP Journal Configuration file') )
        
        product = production_config.lot_id.product_id
        for quant in self:
            if product.product_tmpl_id == quant.product_id.product_tmpl_id and quant.location_id.usage != "customer" :
                return
        super(StockQuant, self)._account_entry_move(move)
    
    def _create_account_move_line(self, move, credit_account_id, debit_account_id, journal_id):
        # group quants by cost
        quant_cost_qty = defaultdict(lambda: 0.0)
        for quant in self:
            quant_cost_qty[quant.cost] += quant.qty

        AccountMove = self.env['account.move']
        for cost, qty in quant_cost_qty.iteritems():
            move_lines = move._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id)
            if move_lines:
                date = self._context.get('force_period_date', fields.Date.context_today(self))
                if move.date :
                    date = move.date
                new_account_move = AccountMove.create({
                    'journal_id': journal_id,
                    'line_ids': move_lines,
                    'date': date,
                    'ref': move.picking_id.name})
                new_account_move.post()
    
