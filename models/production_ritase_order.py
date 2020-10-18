 # -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import time

# import logging
# _logger = logging.getLogger(__name__)

class ProductionRitaseOrder(models.Model):
	_name = "production.ritase.order"
	_inherit = ['mail.thread', 'ir.needaction_mixin']
	_order = 'id desc'
	
	@api.model
	def _default_picking_type(self):
		type_obj = self.env['stock.picking.type']
		company_id = self.env.context.get('company_id') or self.env.user.company_id.id
		types = type_obj.search([('code', '=', 'internal'), ('warehouse_id.company_id', '=', company_id)])
		if not types:
			types = type_obj.search([('code', '=', 'internal'), ('warehouse_id', '=', False)])
		return types[:1]
	
	@api.multi
	def _check_ritase_count(self):
		for rec in self:
			if rec.product_id.tracking == 'none' :
				return True
			rit_by_dt = sum( [ counter_id.ritase_count for counter_id in rec.counter_ids ] )
			rit_by_lot = sum( [ lot_move_id.ritase_count for lot_move_id in rec.lot_move_ids ] )
			if( rit_by_dt != rit_by_lot ):
				return False	
		return True

	READONLY_STATES = {
        'draft': [('readonly', False)] ,
        'confirm': [('readonly', True)] ,
        'done': [('readonly', True)] ,
        'cancel': [('readonly', True)] ,
    }

	name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
	production_order_id = fields.Many2one("production.order", 
        'Production Order', ondelete='restrict', copy=False)
	employee_id	= fields.Many2one('hr.employee', string='Checker', states=READONLY_STATES )
	date = fields.Date('Date', help='',  default=fields.Datetime.now, states=READONLY_STATES )
	picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To', required=True, default=_default_picking_type,\
		help="This will determine picking type of internal shipment", states=READONLY_STATES)
	company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.user.company_id.id, states=READONLY_STATES)
	warehouse_id = fields.Many2one(
            'stock.warehouse', 'Origin Warehouse',
            ondelete="restrict", required=True, states=READONLY_STATES)
	location_id = fields.Many2one(
            'stock.location', 'Origin Location',
			domain=[ ('usage','=',"internal") ],
            ondelete="restrict", required=True, states=READONLY_STATES)
	warehouse_dest_id = fields.Many2one(
			'stock.warehouse', 'Destination Warehouse',
			ondelete="restrict", required=True, states=READONLY_STATES)
	location_dest_id = fields.Many2one(
            'stock.location', 'Destination Location',
			domain=[ ('usage','=',"internal")  ],
            ondelete="restrict", required=True, states=READONLY_STATES)
	shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True, required=True, states=READONLY_STATES )
	buckets = fields.Integer( string="Buckets", default=0, digits=0, states=READONLY_STATES)
	product_id = fields.Many2one('product.product', 'Material', domain=[ ('type','=','product' ) ], required=True, states=READONLY_STATES )
	product_uom = fields.Many2one(
            'product.uom', 'Product Unit of Measure', 
            required=True,
			domain=[ ('category_id.name','=',"Mining")  ],
            default=lambda self: self._context.get('product_uom', False),
			states=READONLY_STATES
			)
	load_vehicle_id = fields.Many2one('fleet.vehicle', 'Load Unit', required=True, states=READONLY_STATES )
	pile_vehicle_id = fields.Many2one('fleet.vehicle', 'Pile Unit', required=True, states=READONLY_STATES )
	ritase_count = fields.Integer( string="Ritase Total", required=True, default=0, digits=0, compute='_compute_ritase_count', readonly=True)
	counter_ids = fields.One2many(
        'production.ritase.counter',
        'ritase_order_id',
        string='Dump Truck Activity',
        copy=True, states=READONLY_STATES )
	lot_move_ids = fields.One2many(
        'production.ritase.lot.move',
        'ritase_order_id',
        string='Lot Movements',
        copy=True, states=READONLY_STATES )
	picking_count = fields.Integer(compute='_compute_picking', string='Pickings', default=0)
	picking_ids = fields.One2many('stock.picking', "ritase_order_id", string='Pickings', copy=False)	
	move_ids = fields.One2many('stock.move', 'ritase_order_id', string='Reservation', readonly=True, ondelete='set null', copy=False)
	
	state = fields.Selection( [
        ('draft', 'Draft'), 
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('done', 'Done'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')

	_constraints = [ 
        (_check_ritase_count, 'Ritase by Lot and Ritase by DT Must Be Same!', ['counter_ids','lot_move_ids'] ) 
        ]
	
	# @api.multi
	# def write(self, values):
	# 	for order in self:
	# 		if order._check_ritase_count() :
	# 			raise UserError(_('Ritase by Lot and Ritase by DT Must Be Same!.'))
	# 	return super(ProductionRitaseOrder, self).write(values)

	@api.multi
	def unlink(self):
		for order in self:
			if order.state in ['confirm', "done"] :
				raise UserError(_('Cannot delete  order which is in state \'%s\'.') %(order.state,))
		return super(ProductionRitaseOrder, self).unlink()

	@api.onchange('warehouse_id', "warehouse_dest_id")	
	def _change_wh(self):
		for order in self:
			return {
				'domain':{
					'location_id':[('location_id','=',order.warehouse_id.view_location_id.id )] ,
					'location_dest_id':[('location_id','=',order.warehouse_dest_id.view_location_id.id )]
					} 
				}
		
	@api.model
	def create(self, values):
		seq = self.env['ir.sequence'].next_by_code('ritase')
		values["name"] = seq
		res = super(ProductionRitaseOrder, self ).create(values)
		return res
		
	@api.depends('counter_ids')	
	def _compute_ritase_count(self):
		for rec in self:
			rec.ritase_count = sum( [ x.ritase_count for x in rec.counter_ids ] )

	@api.multi
	def action_confirm( self ):
		PackOperationLot = self.env['stock.pack.operation.lot'].sudo()
		for order in self:
			order._create_picking()
			picking_ids = order.picking_ids.filtered(lambda r: r.state != 'cancel')
			if len( picking_ids ) != 1 :
				raise UserError(_('1 file Rit only have 1 file Picking. Please cancel another picking file') )
			picking_id = picking_ids[0]
			if picking_id.pack_operation_product_ids:
				pack_operation_product_id = picking_id.pack_operation_product_ids[0]
				if order.product_id.tracking == 'none' :
					pack_operation_product_id.qty_done = order.product_uom._compute_quantity( order.ritase_count , pack_operation_product_id.product_id.uom_id ) 
				else :
					for lot_move_id in order.lot_move_ids:
						PackOperationLot.create({
							'operation_id' : pack_operation_product_id.id,
							'lot_id' : lot_move_id.lot_id.id,
							'qty' : order.product_uom._compute_quantity( lot_move_id.ritase_count, pack_operation_product_id.product_id.uom_id )
						})
				pack_operation_product_id.save()
			order.state = 'confirm'

	@api.multi
	def action_done( self ):
		for order in self:
			ProductionPit = self.env['production.pit'].sudo()
			production_pits = ProductionPit.search([ ( "location_id", "=", order.location_id.id ) ])
			if production_pits and ( not order.production_order_id ):
					raise UserError(_('Unable to Done order %s with PIT origin. Please do this action in Production Order') % (order.name))

			picking_ids = order.picking_ids.filtered(lambda x: x.state not in ('done','cancel'))
			picking_ids.do_new_transfer()
			order.state = 'done'
			
	
	@api.multi
	def action_cancel(self):
		for order in self:
			for pick in order.picking_ids:
				if pick.state == 'done':
					raise UserError(_('Unable to cancel order %s as some receptions have already been done.') % (order.name))

			for pick in order.picking_ids.filtered(lambda r: r.state != 'cancel'):
				pick.action_cancel()

			moves = order.move_ids | order.move_ids.mapped('returned_move_ids')
			moves.filtered(lambda r: r.state != 'cancel').action_cancel()

		self.write({'state': 'cancel'})

	@api.multi
	def action_draft(self):
		self.write({'state': 'draft'})
		return {}

	@api.depends('move_ids')	
	def _compute_picking(self):
		for order in self:
			pickings = self.env['stock.picking']
			moves = order.move_ids | order.move_ids.mapped('returned_move_ids')
			moves = moves.filtered(lambda r: r.state != 'cancel')
			pickings |= moves.mapped('picking_id')
			order.picking_ids = pickings
			order.picking_count = len(pickings)
	
	@api.model
	def _prepare_picking(self):
		StockPickingTypeSudo = self.env['stock.picking.type'].sudo()
		picking_type = StockPickingTypeSudo.search([ 
				("code", '=', 'internal' ),
				("warehouse_id", '=', self.warehouse_id.id ),
				])
		if picking_type :
			self.picking_type_id = picking_type[0]
		
		return {
			'state': 'draft',
			'picking_type_id': self.picking_type_id.id,
			'date': self.date,
			'origin': self.name,
			'location_dest_id': self.location_dest_id.id,
			'location_id': self.location_id.id,
			'company_id': self.company_id.id,
		}
		
	@api.multi
	def _prepare_stock_moves(self, picking):
		""" Prepare the stock moves data for one order line. This function returns a list of
		dictionary ready to be used in stock.move's create()
		"""
		self.ensure_one()
		res = []
		if self.product_id.type not in ['product', 'consu']:
			return res
		qty = 0.0
		for move in self.move_ids.filtered(lambda x: x.state != 'cancel'):
			qty += move.product_qty
		template = {
			'name': self.name or '',
			'product_id': self.product_id.id,
            'product_uom_qty': self.ritase_count ,
			'product_uom': self.product_uom.id,
			'date': self.date,
			'location_id': self.location_id.id,
			'location_dest_id': self.location_dest_id.id,
			'picking_id': picking.id,
			'move_dest_id': False,
			'state': 'draft',
			'ritase_order_id': self.id,
			'picking_type_id': self.picking_type_id.id,
			'procurement_id': False,
			'origin': self.name,
			'route_ids': self.picking_type_id.warehouse_id and [(6, 0, [x.id for x in self.picking_type_id.warehouse_id.route_ids])] or [],
			'warehouse_id': self.warehouse_id.id,
		}
		res.append(template)
		return res

	@api.multi
	def _create_stock_moves(self, picking):
		moves = self.env['stock.move']
		done = self.env['stock.move'].browse()
		for order in self:
			for val in order._prepare_stock_moves(picking):
				done += moves.create(val)
		return done
		
	@api.multi
	def _create_picking(self):
		StockPicking = self.env['stock.picking'].sudo()
		for order in self:
			if ( order.product_id.type in ['product', 'consu'] ):
				pickings = order.picking_ids.filtered(lambda x: x.state not in ('done','cancel'))
				if not pickings:
					res = order._prepare_picking()
					picking = StockPicking.create(res)
				else:
					picking = pickings[0]
				moves = order._create_stock_moves(picking)
				moves = moves.filtered(lambda x: x.state not in ('done', 'cancel')).action_confirm()
				seq = 0
				for move in sorted(moves, key=lambda move: move.date_expected):
					seq += 5
					move.sequence = seq
				moves.force_assign()
				picking.message_post_with_view('mail.message_origin_link',
					values={'self': picking, 'origin': order},
					subtype_id=self.env.ref('mail.mt_note').id)
		return True
		
	@api.multi
	def action_view_picking(self):
		'''
    	This function returns an action that display existing picking orders of given purchase order ids.
        When only one found, show the picking immediately.
        '''
		action = self.env.ref('stock.action_picking_tree')
		result = action.read()[0]

        #override the context to get rid of the default filtering on picking type
		result.pop('id', None)
		result['context'] = {}
		pick_ids = sum([order.picking_ids.ids for order in self], [])
        #choose the view_mode accordingly
		if len(pick_ids) > 1:
			result['domain'] = "[('id','in',[" + ','.join(map(str, pick_ids)) + "])]"
		elif len(pick_ids) == 1:
			res = self.env.ref('stock.view_picking_form', False)
			result['views'] = [(res and res.id or False, 'form')]
			result['res_id'] = pick_ids and pick_ids[0] or False
		return result

class RitaseCounter(models.Model):
	_name = "production.ritase.counter"
	_inherits = {'production.operation.template': 'operation_template_id'}

	ritase_order_id = fields.Many2one("production.ritase.order", string="Ritase", ondelete="restrict" )
	product_id = fields.Many2one("product.product", string="Material", related="ritase_order_id.product_id", ondelete="restrict" )
	location_id = fields.Many2one(
            'stock.location', 'Location',
			related="ritase_order_id.location_id",
			domain=[ ('usage','=',"internal")  ],
            ondelete="restrict" )
	date = fields.Date('Date', help='', related="ritase_order_id.date", readonly=True, default=fields.Datetime.now )
	shift = fields.Selection( [
        ( "1" , '1'),
        ( "2" , '2'),
        ] , string='Shift', index=True, related="ritase_order_id.shift" )

	log_ids = fields.One2many(
        'production.ritase.log',
        'counter_id',
        string='Logs',
        copy=True )
	ritase_count = fields.Integer( string="Ritase Count", required=True, default=0, digits=0, compute='_compute_ritase_count' )
	amount = fields.Float(string='Amount', compute="_compute_amount" )
	
	@api.onchange('vehicle_id')	
	def _change_vehicle_id(self):
		for order in self:
			order.driver_id = order.vehicle_id.driver_id
			
	@api.depends('log_ids')	
	def _compute_ritase_count(self):
		for rec in self:
			rec.ritase_count = len( rec.log_ids )
	
	@api.depends('ritase_count')	
	def _compute_amount(self):
		for rec in self:
			rec.amount = rec.ritase_count *  5000 

	@api.multi
	def post(self):
		'''
		for compute ore cost of production
		'''
		for record in self:
			ProductionConfig = self.env['production.config'].sudo()
			production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
			if not production_config.rit_tag_id :
				raise UserError(_('Please Set Ritase COP Tag in Configuration file') )
			self.env['production.cop.tag.log'].sudo().create({
                    'cop_adjust_id' : record.cop_adjust_id.id,
                    'name' :   'RITASE / ' + record.date,
                    'date' : record.date,
                    'location_id' : record.location_id.id,
                    'tag_id' : production_config.rit_tag_id.id,
                    'product_uom_qty' : record.ritase_count,
                    # 'price_unit' : record.amount /record.ritase_count,
                    'price_unit' : 5000, # TODO : change it programable
                    'amount' : record.amount,
                    'state' : 'posted',
                })
			record.write({'state' : 'posted' })

class RitaseLog(models.Model):
	_name = "production.ritase.log"

	counter_id = fields.Many2one("production.ritase.counter", string="Dump Truck Activity", ondelete="cascade" )
	datetime = fields.Datetime('Date Time', help='',  default=time.strftime("%Y-%m-%d %H:%M:%S") )

class RitaseLotMove(models.Model):
	_name = "production.ritase.lot.move"

	ritase_order_id = fields.Many2one("production.ritase.order", string="Ritase", ondelete="restrict" )
	lot_id = fields.Many2one(
        'stock.production.lot', 'Lot',
		required=True,
        )
	ritase_count = fields.Integer( string="Ritase Count", required=True, default=0, digits=0 )
	

