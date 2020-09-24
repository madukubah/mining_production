# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProductionBlock(models.Model):
    _name = "production.block"
    
    name = fields.Char(string="Name", size=100 , required=True )
    code = fields.Char(string="Code", size=10 , required=True )