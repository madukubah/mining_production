from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class ProductionFleetFactorProductivity( models.Model ):
    _name = 'production.fleet.factor.productivity'
        
    name = fields.Char(string='Name', store=True )
    vehicle_model_id = fields.Many2one(
            'fleet.vehicle.model', 'Vehicle Model',
            ondelete="cascade" )
    activity_id = fields.Many2one(
            'production.activity.definition', 'Activity',
            ondelete="restrict", required=True )
    capacity = fields.Float('Capacity (m^3)', required=True, default=1 )
    swell_factor = fields.Float('Swell Factor', required=True, default=1 )
    fill_factor = fields.Float('Fill Factor', required=True, default=1 )

    @api.model
    def create(self, values):
        vehicle_model_id = self.env['fleet.vehicle.model'].search( [("id", "=", values["vehicle_model_id"] )], limit=1 )
        activity_id = self.env['production.activity.definition'].search( [ ("id", "=", values["activity_id"] )], limit=1 )
        values["name"] = vehicle_model_id[0].name + " / " + activity_id[0].name
        res = super(ProductionFleetFactorProductivity, self ).create(values)
        return res