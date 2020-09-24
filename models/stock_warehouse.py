# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, exceptions, fields, models, _


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    production_to_resupply = fields.Boolean(
        'Mining Production in this Warehouse', default=True,
        help="When products are mining_productiond, they can be mining_productiond in this warehouse.")
    production_pull_id = fields.Many2one(
        'procurement.rule', 'Mining Production Rule')
    mining_type_id = fields.Many2one(
        'stock.picking.type', 'Mining Production Picking Type',
        domain=[('code', '=', 'mining_production')])

    #inherit function | finish
    def create_sequences_and_picking_types(self):
        res = super(StockWarehouse, self).create_sequences_and_picking_types()
        self._create_mining_production_picking_type()
        return res

    #inherit function | finish
    @api.multi
    def get_routes_dict(self):
        result = super(StockWarehouse, self).get_routes_dict()
        for warehouse in self:
            result[warehouse.id]['mining_production'] = [self.Routing(warehouse.lot_stock_id, warehouse.lot_stock_id, warehouse.int_type_id)]
        return result

    def _get_mining_production_route_id(self):
        mining_production_route = self.env.ref('mining_production.route_warehouse0_mining_production', raise_if_not_found=False)
        if not mining_production_route:
            mining_production_route = self.env['stock.location.route'].search([('name', 'like', _('Mining Production'))], limit=1)
        if not mining_production_route:
            raise exceptions.UserError(_('Can\'t find any generic Mining Production route.'))
        return mining_production_route.id

    def _get_production_pull_rules_values(self, route_values):
        if not self.mining_type_id:
            self._create_mining_production_picking_type()
        dummy, pull_rules_list = self._get_push_pull_rules_values(route_values, pull_values={
            'name': self._format_routename(_(' Mining Production')),
            'location_src_id': False,  # TDE FIXME
            'action': 'mining_production',
            'route_id': self._get_mining_production_route_id(),
            'picking_type_id': self.mining_type_id.id,
            'propagate': False,
            'active': True})
        return pull_rules_list

    def _create_mining_production_picking_type(self):
        # TDE CLEANME
        picking_type_obj = self.env['stock.picking.type']
        seq_obj = self.env['ir.sequence']
        for warehouse in self:
            #man_seq_id = seq_obj.sudo().create('name': warehouse.name + _(' Sequence Manufacturing'), 'prefix': warehouse.code + '/MANU/', 'padding')
            wh_stock_loc = warehouse.lot_stock_id
            seq = seq_obj.search([('code', '=', 'production_order')], limit=1)
            other_pick_type = picking_type_obj.search([('warehouse_id', '=', warehouse.id)], order = 'sequence desc', limit=1)
            color = other_pick_type and other_pick_type.color or 0
            max_sequence = other_pick_type and other_pick_type.sequence or 0
            mining_type = picking_type_obj.create({
                'name': _('Mining Production'),
                'warehouse_id': warehouse.id,
                'code': 'mining_production',
                'use_create_lots': True,
                'use_existing_lots': True,
                'sequence_id': seq.id,
                'default_location_src_id': wh_stock_loc.id,
                'default_location_dest_id': wh_stock_loc.id,
                'sequence': max_sequence,
                'color': color})
            warehouse.write({'mining_type_id': mining_type.id})

    def _create_or_update_mining_production_pull(self, routes_data):
        routes_data = routes_data or self.get_routes_dict()
        for warehouse in self:
            routings = routes_data[warehouse.id]['mining_production']
            if warehouse.production_pull_id:
                production_pull = warehouse.production_pull_id
                production_pull.write(warehouse._get_production_pull_rules_values(routings)[0])
            else:
                production_pull = self.env['procurement.rule'].create(warehouse._get_production_pull_rules_values(routings)[0])
        return production_pull


   #inherit function | fininsh
    @api.multi
    def create_routes(self):
        res = super(StockWarehouse, self).create_routes()
        self.ensure_one()
        routes_data = self.get_routes_dict()
        production_pull = self._create_or_update_mining_production_pull(routes_data)
        res['production_pull_id'] = production_pull.id
        return res

    #inherit function | finish
    @api.multi
    def write(self, vals):
        if 'production_to_resupply' in vals:
            if vals.get("production_to_resupply"):
                for warehouse in self.filtered(lambda warehouse: not warehouse.production_pull_id):
                    production_pull = warehouse._create_or_update_mining_production_pull(self.get_routes_dict())
                    vals['production_pull_id'] = production_pull.id
                for warehouse in self:
                    if not warehouse.mining_type_id:
                        warehouse._create_mining_production_picking_type()
                    warehouse.mining_type_id.active = True
            else:
                for warehouse in self:
                    if warehouse.mining_type_id:
                        warehouse.mining_type_id.active = False
                self.mapped('production_pull_id').unlink()
        return super(StockWarehouse, self).write(vals)

    #inherit function | finish
    @api.multi
    def _get_all_routes(self):
        routes = super(StockWarehouse, self).get_all_routes_for_wh()
        routes |= self.filtered(lambda self: self.production_to_resupply and self.production_pull_id and self.production_pull_id.route_id).mapped('production_pull_id').mapped('route_id')
        return routes

    #inherit function |finish
    @api.multi
    def _update_name_and_code(self, name=False, code=False):
        res = super(StockWarehouse, self)._update_name_and_code(name, code)
        # change the mining_production procurement rule name
        for warehouse in self:
            if warehouse.production_pull_id and name:
                warehouse.production_pull_id.write({'name': warehouse.production_pull_id.name.replace(warehouse.name, name, 1)})
        return res
