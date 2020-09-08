 # -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import time

class MiningRitase(models.Model):
	_name = "mining.ritase.order"
	_order = 'id desc'
	
	@api.model
	def _default_picking_type(self):
		type_obj = self.env['stock.picking.type']
		company_id = self.env.context.get('company_id') or self.env.user.company_id.id
		types = type_obj.search([('code', '=', 'internal'), ('warehouse_id.company_id', '=', company_id)])
		if not types:
			types = type_obj.search([('code', '=', 'internal'), ('warehouse_id', '=', False)])
		return types[:1]

	READONLY_STATES = {
        'confirm': [('readonly', True)],
    }

	name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
	partner_id	= fields.Many2one('res.partner', string='Checker', required=True, states=READONLY_STATES )

	date = fields.Date('Date', help='',  default=time.strftime("%Y-%m-%d"), states=READONLY_STATES )
	picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To', required=True, default=_default_picking_type,\
		help="This will determine picking type of internal shipment", states=READONLY_STATES)
	company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.user.company_id.id, states=READONLY_STATES)

	warehouse_id = fields.Many2one(
            'stock.warehouse', 'Origin Warehouse',
            ondelete="restrict", required=True, states=READONLY_STATES)
	location_id = fields.Many2one(
            'stock.location', 'Origin Location',
			domain=[ ('usage','=',"internal")  ],
            ondelete="restrict", required=True, states=READONLY_STATES)
	
	dest_warehouse_id = fields.Many2one(
			'stock.warehouse', 'Destination Warehouse',
			ondelete="restrict", required=True, states=READONLY_STATES)
	dest_location_id = fields.Many2one(
            'stock.location', 'Destination Location',
            ondelete="restrict", required=True, states=READONLY_STATES)
	
	shift = fields.Integer( string="Shift", default=0, digits=0, states=READONLY_STATES)
	buckets = fields.Integer( string="Buckets", default=0, digits=0, states=READONLY_STATES)
	product_id = fields.Many2one('product.product', 'Material', required=True, states=READONLY_STATES )
	product_uom = fields.Many2one(
            'product.uom', 'Product Unit of Measure', 
			# related='product_id.uom_id',
            required=True,
			domain=[ ('category_id.name','=',"Mining")  ],
            default=lambda self: self._context.get('product_uom', False))

	load_vehicle_id = fields.Many2one('fleet.vehicle', 'Load Unit', required=True, states=READONLY_STATES )
	pile_vehicle_id = fields.Many2one('fleet.vehicle', 'Pile Unit', required=True, states=READONLY_STATES )

	ritase_count = fields.Integer( string="Ritase Total", required=True, default=0, digits=0, compute='_compute_ritase_count', readonly=True)
	dumptruck_activity_ids = fields.One2many(
        'mining.dumptruck.activity',
        'ritase_order_id',
        string='Dump Truck Activity',
        copy=True, states=READONLY_STATES )
	picking_count = fields.Integer(compute='_compute_picking', string='Pickings', default=0)
	picking_ids = fields.One2many('stock.picking', "ritase_order_id", string='Pickings', copy=False)	
	move_ids = fields.One2many('stock.move', 'ritase_order_id', string='Reservation', readonly=True, ondelete='set null', copy=False)
	
	state = fields.Selection([
        ('open', 'Open'), 
		('confirm', 'Confirmed'),
		('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='open')

	@api.multi
	def unlink(self):
		for order in self:
			if order.state in ['confirm']:
				raise UserError(_('Cannot delete  order which is in state \'%s\'.') %(order.state,))
		return super(MiningRitase, self).unlink()
		
	@api.model
	def create(self, values):
		seq = self.env['ir.sequence'].next_by_code('ritase')
		values["name"] = seq
		res = super(MiningRitase, self ).create(values)
		return res
		
	@api.depends('dumptruck_activity_ids')	
	def _compute_ritase_count(self):
		for rec in self:
			rec.ritase_count = sum( [ x.ritase_count for x in rec.dumptruck_activity_ids ] )

	@api.multi
	def button_confirm(self):
		self._create_picking()
		self.state = 'confirm'
	
	@api.multi
	def button_cancel(self):
		for order in self:
			for pick in order.picking_ids:
				if pick.state == 'done':
					raise UserError(_('Unable to cancel purchase order %s as some receptions have already been done.') % (order.name))

			for pick in order.picking_ids.filtered(lambda r: r.state != 'cancel'):
				pick.action_cancel()

			moves = order.move_ids | order.move_ids.mapped('returned_move_ids')
			moves.filtered(lambda r: r.state != 'cancel').action_cancel()

		self.write({'state': 'cancel'})

	@api.multi
	def button_draft(self):
		self.write({'state': 'open'})
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
			'location_dest_id': self.dest_location_id.id,
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
			'location_dest_id': self.dest_location_id.id,
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

class DumpTruckActivity(models.Model):
	_name = "mining.dumptruck.activity"

	ritase_order_id = fields.Many2one("mining.ritase.order", string="Ritase", ondelete="restrict" )
	vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
	driver_id	= fields.Many2one('res.partner', string='Driver', required=True )
	log_ids = fields.One2many(
        'mining.dumptruck.activity.log',
        'dumptruck_activity_id',
        string='Logs',
        copy=True )
	ritase_count = fields.Integer( string="Ritase Count", required=True, default=0, digits=0, compute='_compute_ritase_count' )
	
	@api.depends('log_ids')	
	def _compute_ritase_count(self):
		for rec in self:
			rec.ritase_count = len( rec.log_ids )

class DumpTruckActivityLog(models.Model):
	_name = "mining.dumptruck.activity.log"

	dumptruck_activity_id = fields.Many2one("mining.dumptruck.activity", string="Dump Truck Activity", ondelete="restrict" )
	datetime = fields.Datetime('Date Time', help='',  default=time.strftime("%Y-%m-%d %H:%M:%S") )

