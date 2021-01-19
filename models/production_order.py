# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time
from odoo.addons import decimal_precision as dp
import logging
_logger = logging.getLogger(__name__)

class ProductionOrder(models.Model):
    _name = "production.order"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = "id desc"
    
    @api.model
    def _get_default_picking_type(self):
        return self.env['stock.picking.type'].search([
            ('code', '=', 'mining_production'),
            ('warehouse_id.company_id', 'in', [self.env.context.get('company_id', self.env.user.company_id.id), False])],
            limit=1).id
    @api.model
    def _default_config(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0]

    READONLY_STATES = {
        'draft': [('readonly', False)],
        'cancel': [('readonly', True)],
        'confirm': [('readonly', True)],
        'done': [('readonly', True)],
    }

    company_id = fields.Many2one(
        'res.company', 'Company',
        default=lambda self: self.env['res.company']._company_default_get('production.order'),
        required=True)
    production_config_id = fields.Many2one('production.config', string='Production Config', default=_default_config, states=READONLY_STATES )
    name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
    employee_id	= fields.Many2one('hr.employee', string='Grade Control', states=READONLY_STATES )
    user_id = fields.Many2one('res.users', string='User', index=True, track_visibility='onchange', default=lambda self: self.env.user)
    pit_id = fields.Many2one('production.pit', string='Pit', states=READONLY_STATES, domain=[ ('active','=',True)], required=True, change_default=True, index=True, track_visibility='always' )
    
    location_id = fields.Many2one(
            'stock.location', 'Location',
            readonly=True ,
            store=True,copy=True ,
            compute="_onset_pit_id",
            ondelete="restrict" )
    product_id = fields.Many2one(
        'product.product', 'Product',
        domain=[('type', 'in', ['product', 'consu'])],
        readonly=True, required=True,
        states= READONLY_STATES )
    product_tmpl_id = fields.Many2one('product.template', 'Product Template', related='product_id.product_tmpl_id', readonly=True)
    product_qty = fields.Float(
        'Quantity To Produce',
        compute='_compute_ritase',
        default=1.0, digits=dp.get_precision('Product Unit of Measure'),
        readonly=True, required=True, store=True )
    product_uom_id = fields.Many2one(
        'product.uom', 'Product Unit of Measure',
		domain=[ ('category_id.name','=',"Mining")  ],
        oldname='product_uom', readonly=True, required=True,
        states=READONLY_STATES )
    picking_type_id = fields.Many2one(
        'stock.picking.type', 'Picking Type',
        default=_get_default_picking_type, required=True )
    date = fields.Date('Date', help='',  default=fields.Datetime.now , states=READONLY_STATES  )
    shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True, states=READONLY_STATES )
    cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict", states=READONLY_STATES )
    has_moves = fields.Boolean(compute='_has_moves')
    move_ids = fields.One2many(
        'stock.move', 'production_order_id', 'Moves',
        copy=False, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, 
        domain=[('scrapped', '=', False)])
    procurement_group_id = fields.Many2one(
        'procurement.group', 'Procurement Group',
        copy=False)
    procurement_ids = fields.One2many('procurement.order', 'production_order_id', 'Related Procurements')
    rit_ids = fields.One2many('production.ritase.order', 'production_order_id', 'Ritase Orders', states=READONLY_STATES )
    state = fields.Selection([
        ('draft', 'Draft'), 
		('cancel', 'Cancelled'),
		('confirm', 'Confirmed'),
		('done', 'Done'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')
    active = fields.Boolean(
        'Active', default=True,
        help="If unchecked, it will allow you to hide the rule without removing it.")

    # performance
    # dump truck
    dumptruck_ids = fields.Many2many('production.dumptruck.performance', 'production_order_dumptruck_performance_rel', 'production_order_id', 'dumptruck_performance_id', 'Dump Truck', copy=False, states=READONLY_STATES)
    # Heavy Equipment
    he_ids = fields.Many2many('production.he.performance', 'production_order_he_performance_rel', 'production_order_id', 'he_performance_id', 'Heavy Equipment', copy=False, states=READONLY_STATES)


    @api.onchange('product_id', 'picking_type_id', 'company_id')
    def onchange_product_id(self):
        """ Finds UoM of changed product. """
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id.id
            return {'domain': {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}}

    @api.depends("pit_id" )
    def _onset_pit_id(self):
        for rec in self:
            if( rec.pit_id ):
                rec.location_id = rec.pit_id.location_id

    @api.multi
    @api.depends('move_ids')
    def _has_moves(self):
        for order in self:
            order.has_moves = any( order.move_ids )

    @api.multi
    @api.depends('rit_ids')
    def _compute_ritase(self):
        for order in self:
            order.product_qty = sum( [ rit_id.product_uom._compute_quantity( rit_id.ritase_count, order.product_uom_id ) for rit_id in order.rit_ids ] )

    @api.onchange('product_uom_id' )
    def onchange_product_uom_id(self):
        for order in self:
            order.product_qty = sum( [ rit_id.product_uom._compute_quantity( rit_id.ritase_count, order.product_uom_id ) for rit_id in order.rit_ids ] )

    @api.multi
    def action_confirm(self):
        for order in self:
            order._generate_moves()
        self.state = 'confirm'

    @api.multi
    def action_reload( self ):
        RitaseOrder = self.env['production.ritase.order'].sudo()
        ritase_orders = RitaseOrder.search( [ ( "date", "=", self.date ), ( "state", "=", "confirm" ), ( "product_id", "=", self.product_id.id ), ( "location_id", "=", self.location_id.id ) ] )
        self.update({
            'rit_ids': [( 6, 0, ritase_orders.ids )],
        })
        # get dump truck
        dumptruck_ids = []
        for ritase_order in ritase_orders:
            for counter in ritase_order.counter_ids:
                if counter.vehicle_id.id not in dumptruck_ids :
                    dumptruck_ids += [ counter.vehicle_id.id ]
        
        _logger.warning( dumptruck_ids )
        DumptruckPerformance = self.env['production.dumptruck.performance'].sudo()
        for dumptruck_id in dumptruck_ids:
            dumptruck_performances = DumptruckPerformance.search( [ ( "date", "=", self.date ), ( "vehicle_id", "=", dumptruck_id ) ] )
            if not dumptruck_performances : 
                DumptruckPerformance.create({
                        "date" : self.date ,
                        "end_date" : self.date ,
                        "vehicle_id" : dumptruck_id ,
                }).action_reload( )
            else:
                for x in dumptruck_performances :
                    x.action_reload() 
               
        dumptruck_performances = DumptruckPerformance.search( [ ( "date", "=", self.date ), ( "vehicle_id", "in", dumptruck_ids ) ] )
        self.update({
            'dumptruck_ids': [( 6, 0, dumptruck_performances.ids )],
        })
        # ========================
        # get heavy equipment
        he_ids = []
        for ritase_order in ritase_orders:
            for load_vehicle in ritase_order.load_vehicle_ids:
                if load_vehicle.id not in he_ids :
                    he_ids += [ load_vehicle.id ]
            for pile_vehicle in ritase_order.pile_vehicle_ids:
                if pile_vehicle.id not in he_ids :
                    he_ids += [ pile_vehicle.id ]
        
        _logger.warning( he_ids )
        HEPerformance = self.env['production.he.performance'].sudo()
        for he_id in he_ids:
            he_performances = HEPerformance.search( [ ( "date", "=", self.date ), ( "vehicle_id", "=", he_id ) ] )
            if not he_performances : 
                HEPerformance.create({
                        "date" : self.date ,
                        "end_date" : self.date ,
                        "vehicle_id" : he_id ,
                }).action_reload( )
            else:
                for x in he_performances :
                    x.action_reload() 


        he_performances = HEPerformance.search( [ ( "date", "=", self.date ), ( "vehicle_id", "in", he_ids ) ] )
        self.update({
            'he_ids': [( 6, 0, he_performances.ids )],
        })




    @api.multi
    def action_done(self):
        for order in self:
            order.post_inventory()
            # order.action_reload()
            order.rit_ids.action_done()
        self.state = 'done'

    @api.multi
    def action_draft(self):
        # TODO : script to cancel move
        self.action_cancel()
        self.state = 'draft'

    @api.multi
    def action_cancel(self):
        for order in self:
            for move in order.move_ids:
                move.move_lot_ids.unlink()
                if move.state == 'done':
                    raise UserError(_('Unable to cancel order %s as some Stock have already Done.') % (order.name))
            moves = order.move_ids | order.move_ids.mapped('returned_move_ids')
            moves.filtered(lambda r: r.state != 'cancel').action_cancel()
        self.state = 'cancel'

    @api.multi
    def unlink(self):
        for order in self:
            for move in order.move_ids:
                if move.state == 'done':
                    raise UserError(_('Unable to cancel order %s as some Stock have already Done.') % (order.name))
            moves = order.move_ids | order.move_ids.mapped('returned_move_ids')
            moves.filtered(lambda r: r.state != 'cancel').action_cancel()
        return super(ProductionOrder, self ).unlink()
        
    @api.model
    def create(self, values):
        # if not values.get('name', False) or values['name'] == _('New'):
        if values.get('picking_type_id'):
            values['name'] = self.env['stock.picking.type'].browse(values['picking_type_id']).sequence_id.next_by_id()
        else:
            values['name'] = self.env['ir.sequence'].next_by_code('production_order') or _('New')
        if not values.get('procurement_group_id'):
            values['procurement_group_id'] = self.env["procurement.group"].create({'name': values['name']}).id

        # seq = self.env['ir.sequence'].next_by_code('ritase')
        # values["name"] = seq
        res = super(ProductionOrder, self ).create(values)
        return res
    
    @api.multi
    def _generate_moves(self):
        # for production in self:
        self._generate_finished_moves()
        return True

    def _generate_finished_moves(self):
        lots = self.env['mining.stock.move.lots']
        production_config = self.production_config_id
        if not production_config :
            raise UserError(_('Please Set Default Lot In Configuration file') )

        move = self.env['stock.move'].create({
            'name': self.name,
            'date': self.date,
            'product_id': self.product_id.id,
            # 'price_unit': 0,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.product_qty,
            'location_id': self.product_id.property_stock_production.id,
            'location_dest_id': self.location_id.id,
            'move_dest_id': self.procurement_ids and self.procurement_ids[0].move_dest_id.id or False,
            'procurement_id': self.procurement_ids and self.procurement_ids[0].id or False,
            'company_id': self.company_id.id,
            'production_order_id': self.id,
            'origin': self.name,
            'group_id': self.procurement_group_id.id,
        })


        if self.product_id.tracking != 'none' :
            vals = {
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'production_order_id': move.production_order_id.id,
                    'quantity': self.product_qty,
                    'quantity_done': self.product_qty,
                    'lot_id': production_config.lot_id.id,
                }
            lots.create(vals)
        else :
            move.quantity_done = self.product_qty
        return move

    @api.multi
    def post_inventory(self):
        for order in self:
            moves_to_finish = order.move_ids.filtered(lambda x: x.state not in ('done','cancel'))
            moves_to_finish.action_confirm()
            moves_to_finish.action_done()
            
            for move in moves_to_finish:
                #Group quants by lots
                lot_quants = {}
                raw_lot_quants = {}
                if move.has_tracking != 'none':
                    for quant in move.quant_ids:
                        lot_quants.setdefault(quant.lot_id.id, self.env['stock.quant'])
                        raw_lot_quants.setdefault(quant.lot_id.id, self.env['stock.quant'])
                        lot_quants[quant.lot_id.id] |= quant
                
            order.action_assign()
        return True

    @api.multi
    def action_assign(self):
        for production in self:
            move_to_assign = production.move_ids.filtered(lambda x: x.state in ('confirmed', 'waiting', 'assigned'))
            move_to_assign.action_assign()
        return True