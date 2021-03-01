 # -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
# import time
import datetime
from dateutil.relativedelta import relativedelta
from odoo.addons import decimal_precision as dp

import logging
_logger = logging.getLogger(__name__)

class ProductionRitaseOrder(models.Model):
	_name = "production.ritase.order"
	_inherit = ['mail.thread', 'ir.needaction_mixin']
	_order = 'date desc, id desc'
	
	@api.model
	def _default_config(self):
		ProductionConfig = self.env['production.config'].sudo()
		production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
		if not production_config :
			raise UserError(_('Please Set Configuration file') )
		return production_config[0]
		
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
		for order in self:
			if order.product_id.tracking == 'none' :
				order.lot_move_ids.unlink()
				return True
			rit_by_dt = sum( [ counter_id.ritase_count for counter_id in order.counter_ids ] )
			rit_by_lot = sum( [ lot_move_id.ritase_count for lot_move_id in order.lot_move_ids ] )
			if( rit_by_dt != rit_by_lot ):
				return False
		return True

	@api.multi
	def _check_ritase_qty(self):
		for order in self:
			if order.product_id.tracking == 'none' :
				order.lot_move_ids.unlink()
				return True
			qty_by_dt = sum( [ counter_id.product_uom_qty for counter_id in order.counter_ids ] )
			qty_by_lot = sum( [ lot_move_id.product_uom_qty for lot_move_id in order.lot_move_ids ] )
			if( round(order.product_uom_qty, 2) != round(qty_by_lot, 2) ):
			# if( order.product_uom_qty != qty_by_lot ):
				return False
		return True
	
	READONLY_STATES = {
        'draft': [('readonly', False)] ,
        'confirm': [('readonly', True)] ,
        'done': [('readonly', True)] ,
        'cancel': [('readonly', True)] ,
    }

	production_config_id = fields.Many2one('production.config', string='Production Config', default=_default_config, store=True )

	name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
	production_order_id = fields.Many2one("production.order", 
        'Production Order', ondelete='set null', copy=False)
	employee_id	= fields.Many2one('hr.employee', string='Checker', required=True, states=READONLY_STATES )
	date = fields.Date('Date', help='',  default=fields.Datetime.now, states=READONLY_STATES )
	picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To', required=True, default=_default_picking_type,\
		help="This will determine picking type of internal shipment", states=READONLY_STATES)
	company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.user.company_id.id, states=READONLY_STATES)
	# location
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
	# activity
	cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', ondelete="restrict" )
	shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ], string='Shift', index=True, states=READONLY_STATES, default="1" )
	
	product_id = fields.Many2one('product.product', 'Material', domain=[ ('type','=','product' ) ], required=True, states=READONLY_STATES )
	product_uom = fields.Many2one('product.uom', string='Product Unit of Measure', related="product_id.uom_id", ondelete="restrict", store=True,readonly=True )
	# product_uom = fields.Many2one(
    #         'product.uom', 'Product Unit of Measure', 
    #         required=True,
	# 		domain=[ ('category_id.name','=',"Mining")  ],
	# 		ondelete="restrict",
    #         default=lambda self: self._context.get('product_uom', False),
	# 		states=READONLY_STATES
	# 		)
	old_product_uom = fields.Many2one(
            'product.uom', 'Product Unit of Measure (Old)', 
			domain=[ ('category_id.name','=',"Mining")  ],
			ondelete="restrict",
			states=READONLY_STATES
			)
	# fleet
	load_vehicle_id = fields.Many2one('fleet.vehicle', string='Load Unit', copy=True, required=True, states=READONLY_STATES)
	load_vehicle_ids = fields.Many2many('fleet.vehicle', 'ritase_order_load_vehicle_rel', 'ritase_order_id', 'vehicle_id', 'Load Unit', copy=False, states=READONLY_STATES)
	pile_vehicle_ids = fields.Many2many('fleet.vehicle', 'ritase_order_pile_vehicle_rel', 'ritase_order_id', 'vehicle_id', 'Pile Unit', copy=False, states=READONLY_STATES)
	bucket = fields.Integer( string="Buckets", default=0, digits=0, states=READONLY_STATES)
	# factor
	factor_productivity_id = fields.Many2one('production.fleet.factor.productivity', string='Productivity Factor', copy=False, readonly=True, states=READONLY_STATES)
	fleet_model_capacity = fields.Float('Capacity', required=True, default=0, compute='_compute_factors', readonly=True, store=True )
	fleet_model_swell_factor = fields.Float('Swell Factor', required=True, default=0, compute='_compute_factors', readonly=True, store=True )
	fleet_model_fill_factor = fields.Float('Fill Factor', required=True, default=0, compute='_compute_factors', readonly=True,  store=True )

	factor_density_ids = fields.Many2many('production.config.factor.density', 'ritase_density_rel', 'ritase_order_id', 'density_id', string='Densities', copy=True,  states=READONLY_STATES )
	# calculation
	ton_p_ct = fields.Float('Ton/CT', default=0, compute="_compute_ton_p_ct", store=True )
	ritase_count = fields.Integer( string="Ritase Total", required=True, default=0, digits=0, compute='_compute_ritase_count', readonly=True, store=True )
	bucket_count = fields.Integer( string="Buckets Total", required=True, default=0, digits=0, compute='_compute_ritase_count', readonly=True, store=True )
	product_uom_qty = fields.Float('QTY', 
		default=0, 
		digits=dp.get_precision('Product Unit of Measure'),
		compute="_compute_qty", store=True )
	
	# ===================================================================
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
        (_check_ritase_count, 'Ritase by Lot and Ritase by DT Must Be Same!', ['counter_ids','lot_move_ids'] ) ,
        (_check_ritase_qty, 'Tonnase by Lot and Tonnase by DT Must Be Same!', ['counter_ids','lot_move_ids'] ) ,
        ]
	
	@api.multi
	def syncronize(self):
		for order in self:
			order._change_product_id()
			if order.load_vehicle_ids :
				order.load_vehicle_id = order.load_vehicle_ids[0]
				order._change_fleet()
			order._compute_ritase_count()
			if order.old_product_uom == False or order.product_uom != order.product_id.uom_id :
				order.old_product_uom = order.product_uom
				order.product_uom = order.product_id.uom_id
			
	
	@api.multi
	def unlink(self):
		for order in self:
			if order.state in ['confirm', "done"] :
				raise UserError(_('Cannot delete  order which is in state \'%s\'.') %(order.state,))
		return super(ProductionRitaseOrder, self).unlink()

	@api.onchange('warehouse_id', "warehouse_dest_id", "load_vehicle_id")
	def _change_fleet(self):
		for order in self:
			if order.load_vehicle_id :
				vehicle_model_id = order.load_vehicle_id.model_id
				activity_definition_id = self.env['production.activity.definition'].search([ ( "warehouse_id", "=", order.warehouse_id.id ), ( "warehouse_dest_id", "=", order.warehouse_dest_id.id ) ], limit=1)
				if not activity_definition_id :
					raise UserError(_('Cannot Define Mining Activity from %s to %s in %s') %( order.warehouse_id.name, order.warehouse_dest_id.name, order.name ) )
				factor_productivity_id = self.env['production.fleet.factor.productivity'].search([ ( "activity_id", "=", activity_definition_id[0].id ), ( "vehicle_model_id", "=", vehicle_model_id.id ) ], limit=1)
				if not factor_productivity_id :
					raise UserError(_('Cannot Find Fleet [%s] Productivity Factor For Activity %s in %s') % ( vehicle_model_id.name, activity_definition_id[0].name, order.name ) )
				order.factor_productivity_id = factor_productivity_id[0]
		
	@api.onchange('product_id')
	def _change_product_id(self):
		for order in self:
			if order.product_id :
				factor_density_ids = self.env['production.config.factor.density'].sudo().search([( "product_id", "=", order.product_id.id )])
				order.factor_density_ids = factor_density_ids
			else:
				order.factor_density_ids = []

	@api.onchange('warehouse_id', "warehouse_dest_id")
	def _change_wh(self):
		for order in self:
			ProductionConfig = self.env['production.config'].sudo()
			production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
			if not production_config :
				raise UserError(_('Please Set Configuration file') )
			product_ids = [ x.id for x in production_config[0].product_ids ]
			product_ids += [ x.id for x in production_config[0].other_product_ids ]
			product_ids = self.env['product.product'].sudo(  ).search( [ ("id", "in", product_ids ) ] )
			
			return {
				'domain':{
					'location_id':[ ('location_id','=',order.warehouse_id.view_location_id.id ) ] ,
					'location_dest_id':[('location_id','=',order.warehouse_dest_id.view_location_id.id )],
					'product_id':[('id','in', product_ids.ids )],
					}
				}

	@api.model
	def create(self, values):
		seq = self.env['ir.sequence'].next_by_code('ritase')
		values["name"] = seq
		_logger.warning( values )
		X = values["factor_density_ids"]
		del values["factor_density_ids"]
		res = super(ProductionRitaseOrder, self ).create(values)
		factor_density_ids = []
		for x in X :
			# create
			if x[1] :
				factor_density_ids += [ x[1] ]
			# duplicate
			else :
				factor_density_ids += [ x[2][0] ]
		res.factor_density_ids = factor_density_ids
		return res

	@api.depends('factor_productivity_id', "factor_density_ids")	
	def _compute_ton_p_ct(self):
		for order in self:		
			ton_p_ct = order.fleet_model_capacity * sum( [ x.density for x in order.factor_density_ids ] ) * order.fleet_model_swell_factor * order.fleet_model_fill_factor
			order.ton_p_ct = round(ton_p_ct, 2)
	
	@api.depends('factor_productivity_id')
	def _compute_factors(self):
		for order in self:	
			if order.factor_productivity_id	:
				order.fleet_model_capacity = order.factor_productivity_id.capacity
				order.fleet_model_swell_factor = order.factor_productivity_id.swell_factor
				order.fleet_model_fill_factor = order.factor_productivity_id.fill_factor

	@api.depends('ton_p_ct', "bucket", 'counter_ids','lot_move_ids', 'factor_productivity_id', "factor_density_ids")
	def _compute_qty(self):
		for order in self:		
			qty = 0
			if order.product_id.tracking != 'none':
				qty = sum( [ ( x.product_uom_qty  ) for x in order.lot_move_ids ] )
			else:
				qty = sum( [ ( x.product_uom_qty  ) for x in order.counter_ids ] )
			order.product_uom_qty = round( qty, 2)
			
	@api.depends('counter_ids')	
	def _compute_ritase_count(self):
		for order in self:
			order.ritase_count = sum( [ x.ritase_count for x in order.counter_ids ] )
			order.bucket_count = sum( [ ( x.ritase_count * x.bucket  ) for x in order.counter_ids ] )

	@api.onchange('bucket')	
	def _onchange_default_bucket(self):
		for order in self: 
			order.counter_ids.set_bucket( order.bucket )
			order.lot_move_ids.set_bucket( order.bucket )
	
	@api.multi
	def is_from_pit( self ):
		for order in self:
			ProductionPit = self.env['production.pit'].sudo()
			production_pits = ProductionPit.search([ ( "location_id", "=", order.location_id.id ) ])
			if production_pits and ( not order.production_order_id ):
				return True
		return False

	@api.multi
	def action_confirm( self ):
		PackOperationLot = self.env['stock.pack.operation.lot'].sudo()
		for order in self:
			if not order.is_from_pit() :
				order.check_qty()
			if order.product_id.tracking != 'none' :
				if not order.production_config_id.enable_default_lot :
					lot_ids = [ lot_move_id.lot_id.id for lot_move_id in order.lot_move_ids ]
					if order.production_config_id.lot_id.id in lot_ids :
						raise UserError(_('Cannot Create Move With Default Lot, Please Create Unique Lot ( Generated By QAQC )') )

			order._create_picking()
			order.counter_ids.generate_logs()
			picking_ids = order.picking_ids.filtered(lambda r: r.state != 'cancel')
			if len( picking_ids ) != 1 :
				raise UserError(_('1 file Rit only have 1 file Picking. Please cancel another picking file') )
			picking_id = picking_ids[0]
			if picking_id.pack_operation_product_ids:
				pack_operation_product_id = picking_id.pack_operation_product_ids[0]
				if order.product_id.tracking == 'none' :
					qty = order.ton_p_ct * order.bucket_count
					pack_operation_product_id.qty_done = order.product_uom._compute_quantity( qty, order.product_id.uom_id )
				else :
					lot_qty_dict = {}
					for lot_move_id in order.lot_move_ids:
						lot_id = lot_move_id.lot_id.id
						if lot_qty_dict.get( lot_id, False ):
							lot_qty_dict[ lot_id ] +=  lot_move_id.product_uom_qty
						else :
							lot_qty_dict[ lot_id ] = lot_move_id.product_uom_qty

					for lot_id, qty in lot_qty_dict.items():
						PackOperationLot.create({
							'operation_id' : pack_operation_product_id.id,
							'lot_id' : lot_id,
							'qty' : qty
						})

				pack_operation_product_id.save()
			order.state = 'confirm'

	@api.multi
	def check_qty( self ):
		for order in self:
			if order.product_uom_qty == 0 :
				raise UserError(_('%s quantities is 0 Please check it, Something may wrong') % ( order.name ))
			lot_qty_dict = {}
			if order.product_id.tracking != 'none' :
				for lot_move_id in order.lot_move_ids:
					lot_id = lot_move_id.lot_id.id
					if lot_qty_dict.get( lot_id, False ):
						lot_qty_dict[ lot_id ] +=  lot_move_id.product_uom_qty
					else :
						lot_qty_dict[ lot_id ] = lot_move_id.product_uom_qty

				for lot_id, qty in lot_qty_dict.items():
					product_qty = order.product_id.with_context({'location' : order.location_id.id, 'lot_id' : lot_id })
					if qty > product_qty.qty_available :
						lot = self.env['stock.production.lot'].sudo().search([("id", "=", lot_id )])
						raise UserError(_('Not Enought %s quantities in %s .Please Adjust Quantities First or Maybe its On The Way') % ( lot.name, order.location_id.name))
			else :
				product_qty = order.product_id.with_context({'location' : order.location_id.id })
				if order.product_uom_qty > product_qty.qty_available :
					raise UserError(_('Not Enought %s quantities in %s .Please Adjust Quantities First or Maybe its On The Way') % ( order.product_id.name , order.location_id.name))
			
	@api.multi
	def action_done( self ):
		for order in self:
			if order.is_from_pit() :
				raise UserError(_('Unable to Done order %s with PIT origin. Please do this action in Production Order') % (order.name))
			order.check_qty()

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
            'product_uom_qty': self.product_uom_qty ,
			'product_uom': self.product_uom.id,
			'date': self.date,
			'date_expected': self.date,
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
	# _inherits = {'production.operation.template': 'operation_template_id'}
	_order = 'driver_id asc ,date asc'

	@api.model
	def _default_config(self):
		ProductionConfig = self.env['production.config'].sudo()
		production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
		if not production_config :
			raise UserError(_('Please Set Configuration file') )
		return production_config[0]

	production_config_id = fields.Many2one('production.config', string='Config', default=_default_config)

	ritase_order_id = fields.Many2one("production.ritase.order", string="Ritase", ondelete="cascade" )
	name = fields.Char(compute='_compute_name', store=True)
	location_id = fields.Many2one(
            'stock.location', 'Location',
			domain=[ ('usage','=',"internal")  ],
			related="ritase_order_id.location_id",
			store=True,
            ondelete="restrict" )
	location_dest_id = fields.Many2one(
            'stock.location', 'Location',
			domain=[ ('usage','=',"internal")  ],
			related="ritase_order_id.location_dest_id",
			store=True,
            ondelete="restrict" )
	date = fields.Date('Date', help='', related="ritase_order_id.date", readonly=True, default=fields.Datetime.now, store=True )
	cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', related="ritase_order_id.cost_code_id", ondelete="restrict", store=True )

	# vehicle n driver
	vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle' )
	driver_id	= fields.Many2one('res.partner', string='Driver' )

	cop_adjust_id	= fields.Many2one('production.cop.adjust', string='COP Adjust', copy=False)
	state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], string='Status',
		required=True, readonly=True, copy=False, default='draft' )

	shift = fields.Selection([
        ( "1" , '1'),
        ( "2" , '2'),
        ] , string='Shift', index=True, 
		store=True )
	log_ids = fields.One2many(
        'production.ritase.log',
        'counter_id',
        string='Logs',
        copy=True )

	#calculation
	product_id = fields.Many2one("product.product", string="Material", related="ritase_order_id.product_id", ondelete="restrict" )
	product_uom = fields.Many2one(
            'product.uom', 'Product Unit of Measure', 
            required=True,
			domain=[ ('category_id.name','=',"Mining")  ],
			related='ritase_order_id.product_uom'
			)
	ritase_count = fields.Integer( string="Ritase Count", required=True, default=0, digits=0 )
	bucket = fields.Integer( string="Buckets", default=0, digits=0 )
	ton_p_ct = fields.Float('Ton/CT', default=0, related='ritase_order_id.ton_p_ct' )
	product_uom_qty = fields.Float('QTY', 
		default=0, 
		digits=dp.get_precision('Product Unit of Measure'),
		compute="_compute_qty" )

	# logs
	start_datetime = fields.Datetime('Start Date Time', help='',  default=fields.Datetime.now, store=True )
	end_datetime = fields.Datetime('End Date Time', help='' , store=True)
	minutes = fields.Float('Minutes', readonly=True, compute="_compute_minutes" )
	amount = fields.Float(string='Amount', compute="_compute_amount", store=True )
	
	@api.multi
	def repair(self):
		for record in self:	
			operation = record.operation_template_id
			_logger.warning( operation.vehicle_id.id )
			record.update({
				'vehicle_id' : operation.vehicle_id.id,
				'driver_id' : operation.driver_id.id,
			})
			_logger.warning( record.vehicle_id )

	@api.depends( 'vehicle_id', 'date' )
	def _compute_name(self):
		for record in self:
			name = record.vehicle_id.name
			if not name:
				name = record.date
			elif record.date:
				name += ' / ' + record.date
			record.name = name

	@api.onchange('vehicle_id')	
	def _change_vehicle_id(self):
		for record in self:
			record.driver_id = record.vehicle_id.driver_id
				
	@api.depends('ton_p_ct', "bucket", "ritase_count", 'ritase_order_id.factor_productivity_id', "ritase_order_id.factor_density_ids")
	def _compute_qty(self):
		for record in self:		
			qty = record.ton_p_ct * record.ritase_count * record.bucket
			qty = record.product_uom._compute_quantity( qty, record.product_id.uom_id )
			record.product_uom_qty = round( qty, 2)

	@api.onchange( 'ritase_order_id' )
	def _change_ritase_order_id(self):
		for record in self:
			if record.ritase_order_id :
				record.shift = record.ritase_order_id.shift
				# record.location_id = record.ritase_order_id.location_id
				# record.location_dest_id = record.ritase_order_id.location_dest_id
				record.bucket = record.ritase_order_id.bucket

	@api.onchange( 'date' )
	def _set_date(self):
		for record in self:
			record.start_datetime = record.date
			record.end_datetime = record.date

	@api.onchange('start_datetime', 'end_datetime')
	def _compute_minutes(self):
		for record in self:
			if record.start_datetime and record.end_datetime :
				start = datetime.datetime.strptime(record.start_datetime, '%Y-%m-%d %H:%M:%S')
				ends = datetime.datetime.strptime(record.end_datetime, '%Y-%m-%d %H:%M:%S')
				diff = relativedelta(ends, start)
				record.minutes = diff.minutes + ( diff.hours * 60 )

	def set_bucket(self, bucket):
		for record in self:
			record.bucket = bucket

	def generate_logs(self):
		for record in self:
			# _logger.warning( "generate_logs" )
			record.log_ids.unlink()
			seconds = record.minutes * 60
			interval = seconds / record.ritase_count
			start = datetime.datetime.strptime(record.start_datetime , '%Y-%m-%d %H:%M:%S')
			end = datetime.datetime.strptime(record.end_datetime , '%Y-%m-%d %H:%M:%S')
			for i in range( record.ritase_count - 1 ) :
				self.env['production.ritase.log'].create({
					"counter_id" : record.id ,
					"datetime" : start  ,
				})
				start = start + datetime.timedelta( 0, interval )
			self.env['production.ritase.log'].create({
				"counter_id" : record.id ,
				"datetime" : end  ,
			})
		return True

	@api.onchange('vehicle_id')
	def _change_vehicle_id(self):
		for record in self:
			record.driver_id = record.vehicle_id.driver_id
			
	@api.depends('log_ids')	
	def _compute_ritase_count(self):
		for record in self:
			record.ritase_count = len( record.log_ids )
	
	@api.depends('ritase_count')	
	def _compute_amount(self):
		for record in self:
			record.amount = record.ritase_count *  record.production_config_id.rit_price_unit 

	@api.multi
	def post(self):
		'''
		for compute ore cost of production
		'''
		for record in self:
			if record.state != 'posted' and record.cop_adjust_id :
				self.env['production.cop.tag.log'].sudo().create({
						# 'cop_adjust_id' : record.cop_adjust_id.id,
						'name' :   'RITASE / ' + record.date,
						'date' : record.date,
						'location_id' : record.location_id.id,
						'tag_id' : record.production_config_id.rit_tag_id.id,
						'product_uom_qty' : record.ritase_count,
						# 'price_unit' : record.amount /record.ritase_count,
						'price_unit' : record.production_config_id.rit_price_unit, # TODO : change it programable
						'amount' : record.amount,
						'state' : 'posted',
                    	'from_cop_adjust' : True,
					})
				record.write({ 'state' : 'posted' })
			else :
				raise UserError(_('Ritase Error') )

class RitaseLog(models.Model):
	_name = "production.ritase.log"
	_order = 'datetime asc'

	counter_id = fields.Many2one("production.ritase.counter", string="Dump Truck Activity", ondelete="cascade" )
	vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', related="counter_id.vehicle_id", store=True)
	cost_code_id = fields.Many2one('production.cost.code', string='Cost Code', related="counter_id.cost_code_id", store=True)
	datetime = fields.Datetime('Date Time', help='',  default=fields.Datetime.now )

class RitaseLotMove(models.Model):
	_name = "production.ritase.lot.move"

	ritase_order_id = fields.Many2one("production.ritase.order", string="Ritase", ondelete="cascade" )
	lot_id = fields.Many2one(
        'stock.production.lot', 'Lot',
		required=True,
        )
	location_id = fields.Many2one(
            'stock.location', 'Location',
			domain=[ ('usage','=',"internal")  ],
			related='ritase_order_id.location_id',
            ondelete="restrict" )
	#calculation
	product_id = fields.Many2one("product.product", string="Material", related="ritase_order_id.product_id", ondelete="restrict" )
	product_uom = fields.Many2one(
            'product.uom', 'Product Unit of Measure', 
            # required=True,
			domain=[ ('category_id.name','=',"Mining")  ],
			related='ritase_order_id.product_uom'
			)
	ritase_count = fields.Integer( string="Ritase Count", required=True, default=0, digits=0 )
	bucket = fields.Integer( string="Bucket", required=True, default=0, digits=0 )
	ton_p_ct = fields.Float('Ton/CT', default=0, related='ritase_order_id.ton_p_ct' )
	product_uom_qty = fields.Float('QTY', 
		default=0, 
		digits=dp.get_precision('Product Unit of Measure'),
		compute="_compute_qty" )

	@api.multi
	def check_qty( self ):
		for record in self:		
			product_qty = record.product_id.with_context({'location' : record.location_id.id, 'lot_id' : record.lot_id.id })
			if record.product_uom_qty > product_qty.qty_available :
					raise UserError(_('Not Enought %s quantities in %s .Please Adjust Quantities First or Maybe its On The Way') % (record.lot_id.name, record.location_id.name))

	@api.depends('ton_p_ct', "bucket", "ritase_count", 'ritase_order_id.factor_productivity_id', "ritase_order_id.factor_density_ids")
	def _compute_qty(self):
		for record in self:		
			qty = record.ton_p_ct * record.ritase_count * record.bucket
			qty = record.product_uom._compute_quantity( qty, record.product_id.uom_id )
			record.product_uom_qty = round( qty, 2)

	def set_bucket(self, bucket):
		for record in self:
			record.bucket = bucket