# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

import datetime
from dateutil.relativedelta import relativedelta
_logger = logging.getLogger(__name__)

class ProductionProductionReport(models.TransientModel):
    _name = 'production.production.report'

    @api.model
    def _default_tag(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )
        return production_config[0].hm_vehicle_tag_id
    
    @api.onchange('pit_id', "location_id")	
    def _default_product(self):
        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )

        return production_config[0].product_ids

    @api.model
    def default_get(self, fields):
        res = super(ProductionProductionReport, self).default_get(fields)

        ProductionConfig = self.env['production.config'].sudo()
        production_config = ProductionConfig.search([ ( "active", "=", True ) ]) 
        if not production_config :
            raise UserError(_('Please Set Configuration file') )

        res[ "product_id" ] = production_config.lot_id.product_id.id
        return res

    start_date = fields.Date('Start Date', required=True, default="2021-01-01" )
    end_date = fields.Date(string="End Date", required=True, default="2021-01-31")
    
    pit_ids = fields.Many2many('production.pit', 'production_report_pit_rel', 'report_id', 'pit_id', string='Pits' )

    product_id = fields.Many2one('product.product', string='Main Material' )
    waste_ids = fields.Many2many('product.product', 'production_report_waste_rel', 'report_id', 'product_id', string='Waste Materials' )
    product_ids = fields.Many2many('product.product', 'production_report_product_rel', 'report_id', 'product_id', string='Materials', default=_default_product )

    @api.multi
    def action_print(self):
        start = datetime.datetime.strptime( self.start_date, '%Y-%m-%d')
        end = datetime.datetime.strptime( self.end_date, '%Y-%m-%d')
        days = abs( relativedelta(end, start).days )

        product_uom_dict = {}
        for product_id in self.product_ids :
            product_uom_dict[ product_id.name ] = {
                "rit" : 0,
                "wmt" : 0,
            }
        
        _location_ids = []
        _waste_ids = [ x.id for x in self.waste_ids ]
        pit_product_dict = {}
        for pit_id in self.pit_ids :
            _location_ids += [ pit_id.location_id.id ]
            pit_product_dict[ pit_id.location_id.name ] = {}
            pit_product_dict[ pit_id.location_id.name ]["products"] = {}
            pit_product_dict[ pit_id.location_id.name ][ "stripping_ratio" ] = 0
            for product_id in self.product_ids :
                pit_product_dict[ pit_id.location_id.name ]["products"][ product_id.name ] = {
                    "rit" : 0,
                    "wmt" : 0,
                }

        date_production_dict ={}
        dates = []
        date = start.strftime( '%Y-%m-%d')
        for i in range( days+1 ) :
            dates += [ date ]
            date_production_dict[ date ] = {}
            date_production_dict[ date ][ "stripping_ratio" ] = 0
            date_production_dict[ date ]["losstime"] = {
                "rainy" : 0,
                "slippery" : 0,
            }
            # compute total losstime
            date_production_dict["losstime"] = {
                "rainy" : 0,
                "slippery" : 0,
            }
            for pit_id in self.pit_ids :
                date_production_dict[ date ][ pit_id.location_id.name ] = {}
                for product_id in self.product_ids :
                    date_production_dict[ date ][ pit_id.location_id.name ][ product_id.name ] = {
                        "rit" : 0,
                        "wmt" : 0,
                    }
                    date_production_dict[ date ][ product_id.name ] = {
                        "rit" : 0,
                        "wmt" : 0,
                    }
            start += datetime.timedelta(days=1)
            date = start.strftime( '%Y-%m-%d')
        
        # production_orders
        # production_orders = self.env['production.order'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( 'state', '=', "done" ), ( 'pit_id', 'in', self.pit_ids.ids ) ] )
        # for production_order in production_orders:
        #     date = production_order.date
        #     product_name = production_order.product_id.name
        #     location_name = production_order.location_id.name
        #     if date_production_dict.get( date , False):
        #         if date_production_dict[ date ].get( location_name , False):
        #             if date_production_dict[ date ][location_name].get( product_name , False):
        #                 date_production_dict[ date ][location_name][ product_name ]["wmt"] += production_order.product_qty
        #                 date_production_dict[ date ][location_name][ product_name ]["rit"] += sum( [ rit.ritase_count for rit in production_order.rit_ids ] )

        #                 pit_product_dict[location_name]["products"][ product_name ]["wmt"] += production_order.product_qty
        #                 pit_product_dict[location_name]["products"][ product_name ]["rit"] += sum( [ rit.ritase_count for rit in production_order.rit_ids ] )

        #                 date_production_dict[ date ][ product_name ]["wmt"] += production_order.product_qty
        #                 date_production_dict[ date ][ product_name ]["rit"] += sum( [ rit.ritase_count for rit in production_order.rit_ids ] )

        #                 product_uom_dict[ product_name ]["wmt"] += production_order.product_qty
        #                 product_uom_dict[ product_name ]["rit"] += sum( [ rit.ritase_count for rit in production_order.rit_ids ] )

        # ritase_orders
        ritase_orders = self.env['production.ritase.order'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ), ( "location_id", "in", _location_ids ), ( "product_id", "in", self.product_ids.ids ) ] )
        for ritase_order in ritase_orders:
            date = ritase_order.date
            product_name = ritase_order.product_id.name
            location_name = ritase_order.location_id.name
            if date_production_dict.get( date , False):
                if date_production_dict[ date ].get( location_name , False):
                    if date_production_dict[ date ][location_name].get( product_name , False):
                        date_production_dict[ date ][location_name][ product_name ]["wmt"] += ritase_order.product_uom._compute_quantity( ritase_order.product_uom_qty, ritase_order.product_id.uom_id )
                        date_production_dict[ date ][location_name][ product_name ]["rit"] += ritase_order.ritase_count

                        pit_product_dict[location_name]["products"][ product_name ]["wmt"] += ritase_order.product_uom._compute_quantity( ritase_order.product_uom_qty, ritase_order.product_id.uom_id )
                        pit_product_dict[location_name]["products"][ product_name ]["rit"] += ritase_order.ritase_count

                        date_production_dict[ date ][ product_name ]["wmt"] += ritase_order.product_uom._compute_quantity( ritase_order.product_uom_qty, ritase_order.product_id.uom_id )
                        date_production_dict[ date ][ product_name ]["rit"] += ritase_order.ritase_count

                        product_uom_dict[ product_name ]["wmt"] += ritase_order.product_uom._compute_quantity( ritase_order.product_uom_qty, ritase_order.product_id.uom_id )
                        product_uom_dict[ product_name ]["rit"] += ritase_order.ritase_count

        # ritase_orders
        losstimes = self.env['production.losstime'].search([ ( 'date', '>=', self.start_date ), ( 'date', '<=', self.end_date ) ] )
        for losstime in losstimes:
            date_production_dict[ losstime.date ]["losstime"][ losstime.losstime_type ] += losstime.hour
            date_production_dict["losstime"][ losstime.losstime_type ] += losstime.hour

        # SR per day
        for date in dates :
            date_production_dict[ date ][ "stripping_ratio" ] = 0
            main = 0
            waste = 0
            for product_id in self.product_ids :
                if product_id.id == self.product_id.id :
                    main += date_production_dict[ date ][ product_id.name ]["wmt"]
                elif product_id.id in _waste_ids :
                    waste += date_production_dict[ date ][ product_id.name ]["wmt"]
            if main != 0 :
                date_production_dict[ date ][ "stripping_ratio" ] = round( ( waste / main ) ,2)
        
        # SR all
        date_production_dict[ "stripping_ratio" ] = 0
        main = 0
        waste = 0
        for product_id in self.product_ids :
            if product_id.id == self.product_id.id :
                main += product_uom_dict[ product_id.name ]["wmt"]
            elif product_id.id in _waste_ids :
                waste += product_uom_dict[ product_id.name ]["wmt"]
        if main != 0 :
            date_production_dict[ "stripping_ratio" ] = round( ( waste / main ) ,2)
                
        # SR per PIT
        for pit_id in self.pit_ids :
            main = 0
            waste = 0
            for product_id in self.product_ids :
                if product_id.id == self.product_id.id :
                    main += pit_product_dict[ pit_id.location_id.name ]["products"][ product_id.name ]["wmt"]
                elif product_id.id in _waste_ids :
                    waste += pit_product_dict[ pit_id.location_id.name ]["products"][ product_id.name ]["wmt"]
            if main != 0 :
                pit_product_dict[ pit_id.location_id.name ][ "stripping_ratio" ] = round( ( waste / main ) ,2)
            else :
                pit_product_dict[ pit_id.location_id.name ][ "stripping_ratio" ] = 0
            

        datas = {
            'ids': self.ids,
            'model': 'production.production.report',
            'form': date_production_dict,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'dates': dates,
            'pit_product_dict': pit_product_dict,
            "product_uom_dict" : product_uom_dict,
        }
        # _logger.warning( datas )
        return self.env['report'].with_context( landscape=True ).get_action(self,'mining_production.production_production_temp', data=datas)
