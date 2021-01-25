# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time
from odoo.addons import decimal_precision as dp
import logging
_logger = logging.getLogger(__name__)

class ProductionBatch(models.Model):
    _name = "production.batch"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = "date desc, id desc"
    
    @api.model
    def _default_product(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        product_ids = [ x.id for x in production_config[0].product_ids ]
        product_ids = self.env['product.product'].sudo(  ).search( [ ("id", "in", product_ids ) ] )
        return product_ids.ids

    READONLY_STATES = {
        'draft': [('readonly', False)],
        'cancel': [('readonly', True)],
        'confirm': [('readonly', True)],
        'done': [('readonly', True)],
    }

    name = fields.Char(string="Name", size=100 , required=True, readonly=True, default="NEW")
    date = fields.Date('Date', help='',  default=fields.Datetime.now , states=READONLY_STATES  )
    product_ids = fields.Many2many('product.product', 'production_batch_product_rel', 'production_batch_id', 'product_id', string='Materials', default=_default_product, states=READONLY_STATES )
    employee_id	= fields.Many2one('hr.employee', string='Grade Control', states=READONLY_STATES )
    user_id = fields.Many2one('res.users', string='User', index=True, track_visibility='onchange', default=lambda self: self.env.user)
    pit_id = fields.Many2one('production.pit', string='Pit', states=READONLY_STATES, domain=[ ('active','=',True)], required=True, change_default=True, index=True, track_visibility='always' )
    location_id = fields.Many2one(
            'stock.location', 'Location',
            readonly=True ,
            store=True,copy=True ,
            compute="_onset_pit_id",
            ondelete="restrict" )

    state = fields.Selection([
        ('draft', 'Draft'), 
		('cancel', 'Cancelled'),
		('confirm', 'Confirmed'),
		('done', 'Done'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')

    production_order_ids = fields.One2many('production.order', 'production_batch_id', 'Production Orders', states=READONLY_STATES )
    # dump truck
    dumptruck_ids = fields.Many2many('production.dumptruck.performance', 'production_batch_dumptruck_performance_rel', 'production_batch_id', 'dumptruck_performance_id', 'Dump Truck', copy=False, states=READONLY_STATES)
    # Heavy Equipment
    he_ids = fields.Many2many('production.he.performance', 'production_batch_he_performance_rel', 'production_batch_id', 'he_performance_id', 'Heavy Equipment', copy=False, states=READONLY_STATES)

    # cost analisys
    cost_ids = fields.Many2many('fleet.vehicle.cost', 'production_batch_cost_rel', 'production_batch_id', 'cost_id', 'Vehicle Cost', copy=False, states=READONLY_STATES)
    counter_ids = fields.Many2many('production.ritase.counter', 'production_batch_counter_rel', 'production_batch_id', 'counter_id', 'Ritase', copy=False, states=READONLY_STATES)
    hourmeter_ids = fields.Many2many('production.vehicle.hourmeter.log', 'production_batch_hourmeter_rel', 'production_batch_id', 'hourmeter_id', 'Hourmeter', copy=False, states=READONLY_STATES)
    
    total_amount = fields.Float(string='Total Cost (IDR)', compute="_compute_amount" )

    @api.depends("cost_ids", "counter_ids", "hourmeter_ids" )
    def _compute_amount(self):
        for record in self:
            sum_rit = sum( [ rit.amount for rit in record.counter_ids ] )
            sum_hm = sum( [ hourmeter.amount for hourmeter in record.hourmeter_ids ] )
            sum_vehicle_cost = sum( [ cost.amount for cost in record.cost_ids ] )

            record.total_amount = sum_rit + sum_hm + sum_vehicle_cost

    @api.multi
    def action_reload( self ):
        self.ensure_one()
        production_order_ids = []
        for product_id in self.product_ids:
            RitaseOrder = self.env['production.ritase.order'].sudo()
            ritase_orders = RitaseOrder.search( [ ( "date", "=", self.date ), ( "state", "=", "confirm" ), ( "product_id", "=", product_id.id ), ( "location_id", "=", self.location_id.id ) ] )
            if ritase_orders :
                production_orders = self.env['production.order'].sudo().search( [ ( "date", "=", self.date ), ( "product_id", "=", product_id.id ), ( "location_id", "=", self.location_id.id ) ] )
                if production_orders :
                    for production_order in production_orders:
                        production_order.action_reload()
                        production_order_ids += [ production_order.id ]
                    continue
                else :
                    production = self.env['production.order'].sudo().create({
                        "date" : self.date,
                        "product_id" : product_id.id,
                        "product_uom_id" : product_id.uom_id.id,
                        "pit_id" : self.pit_id.id,
                        "employee_id" : self.employee_id.id,
                    })
                    production.action_reload()
                    production_order_ids += [ production.id ]
        
        self.update({
            'production_order_ids': [( 6, 0, production_order_ids )],
        })
        self.get_performance()

    @api.multi
    def get_performance(self):
        for order in self:
            dumptruck_ids = []
            he_ids = []
            DumptruckPerformance = self.env['production.dumptruck.performance'].sudo()
            HEPerformance = self.env['production.he.performance'].sudo()
            for production_order in order.production_order_ids:
                ritase_orders = production_order.rit_ids
                # get dump truck
                for ritase_order in ritase_orders:
                    for counter in ritase_order.counter_ids:
                        if counter.vehicle_id.id not in dumptruck_ids :
                            dumptruck_ids += [ counter.vehicle_id.id ]
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
                            x.update( {
                                "date" : self.date ,
                                "end_date" : self.date ,
                            } )
                            x.action_reload() 
                # ========================
                # get heavy equipment
                for ritase_order in ritase_orders:
                    for load_vehicle in ritase_order.load_vehicle_ids:
                        if load_vehicle.id not in he_ids :
                            he_ids += [ load_vehicle.id ]
                    for pile_vehicle in ritase_order.pile_vehicle_ids:
                        if pile_vehicle.id not in he_ids :
                            he_ids += [ pile_vehicle.id ]
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
                            x.update( {
                                "date" : self.date ,
                                "end_date" : self.date ,
                            } )
                            x.action_reload() 

            dumptruck_performances = DumptruckPerformance.search( [ ( "date", "=", self.date ), ( "vehicle_id", "in", dumptruck_ids ) ] )
            self.update({
                'dumptruck_ids': [( 6, 0, dumptruck_performances.ids )],
            })
            he_performances = HEPerformance.search( [ ( "date", "=", self.date ), ( "vehicle_id", "in", he_ids ) ] )
            self.update({
                'he_ids': [( 6, 0, he_performances.ids )],
            })
            
            # TODO : for cost analysis
            RitaseCounter = self.env['production.ritase.counter'].sudo()
            ritase_counter = RitaseCounter.search( [ ( "vehicle_id", "in", dumptruck_ids ), ( "date", "=", self.date ) ] )
            self.update({
                'counter_ids': [( 6, 0, ritase_counter.ids )],
            })
            
            HourmeterLog = self.env['production.vehicle.hourmeter.log'].sudo()
            hourmeter_log = HourmeterLog.search( [ ( "vehicle_id", "in", he_ids ), ( "date", "=", self.date ) ] )
            self.update({
                'hourmeter_ids': [( 6, 0, hourmeter_log.ids )],
            })
            
            he_ids += dumptruck_ids
            VehicleCost = self.env['fleet.vehicle.cost'].sudo()
            vehicle_costs = VehicleCost.search( [ ( "vehicle_id", "in", he_ids ), ( "date", "=", self.date ) ] )
            vehicle_costs_ids = [ vehicle_cost.id for vehicle_cost in vehicle_costs if vehicle_cost.cost_subtype_id.is_consumable ]
            self.update({
                'cost_ids': [( 6, 0, vehicle_costs_ids )],
            })

    @api.multi
    def unlink(self):
        for order in self:
            for production_order in order.production_order_ids:
                if production_order.state == 'done':
                    raise UserError(_('Unable to cancel order %s as some Stock have already Done.') % (order.name))
        return super(ProductionBatch, self ).unlink()
        
    @api.multi
    def action_cancel(self):
        for order in self:
            for production_order in order.production_order_ids:
                if production_order.state == 'done':
                    raise UserError(_('Unable to cancel order %s as some Stock have already Done.') % (order.name))
            order.production_order_ids.action_cancel()
            order.state = 'cancel'

    @api.multi
    def action_done(self):
        self.ensure_one()
        self.production_order_ids.action_done( )
        self.state = 'done'

    @api.multi
    def action_draft(self):
        self.ensure_one()
        self.production_order_ids.action_draft( )
        self.state = 'draft'

    @api.multi
    def action_confirm(self):
        self.ensure_one()
        self.production_order_ids.action_confirm( )
        self.state = 'confirm'

        # for production_order in self.production_order_ids:
        #     production_order.action_confirm( )

    @api.depends("pit_id" )
    def _onset_pit_id(self):
        for rec in self:
            if( rec.pit_id ):
                rec.location_id = rec.pit_id.location_id

    @api.model
    def create(self, values):
        values['name'] = self.env['ir.sequence'].next_by_code('production_batch') or _('New')

        res = super(ProductionBatch, self ).create(values)
        return res
    