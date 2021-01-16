# -*- coding: utf-8 -*-

{
    'name': 'Mining Production',
    'version': '1.0',
    'author': 'Technoindo.com',
    'category': 'Mining',
    'depends': [
        'fleet',
        'fleet_losstime',
        'stock',
        'account',
        'stock_account',
    ],
    'data': [
        "views/stock_warehouse_views.xml",
        "views/stock_move_views.xml",
        'views/menu.xml',
        "views/production_config.xml",
        "views/production_hourmeter_order.xml",
        "views/production_operation_template.xml",
        "views/production_ritase_order.xml",
        'views/production_watertruck_order.xml',
        "views/stock_views.xml",
        "views/cost_code.xml",
        "views/production_block.xml",
        "views/production_losstime.xml",
        "views/production_pit.xml",
        "views/production_order.xml",
        "views/procurement_views.xml",
        "views/production_cop_adjust.xml",
        "views/fleet_service_type.xml",
        "views/fleet.xml",
        "views/production_cop_tag_log.xml",
        "views/production_cop_tag.xml",
        "views/production_losstime_accumulation.xml",

        "wizard/production_cop_report.xml",
        "wizard/production_ritase_report.xml",
        "wizard/production_hourmeter_report.xml",
        "wizard/production_watertruck_report.xml",

        "report/production_cop_report.xml",
        "report/production_cop_temp.xml",
        "report/production_ritase_report.xml",
        "report/production_ritase_temp.xml",
        "report/production_hourmeter_report.xml",
        "report/production_hourmeter_temp.xml",
        "report/production_watertruck_report.xml",
        "report/production_watertruck_temp.xml",

        "data/production_data.xml",

        "security/security.xml",
        "security/ir.model.access.csv",

        "seed/production_ritase_seed.xml",
        "seed/production_houtmeter_seed.xml",
    ],
    'qweb': [
        # 'static/src/xml/cashback_templates.xml',
    ],
    'demo': [
        # 'demo/sale_agent_demo.xml',
    ],
    "installable": True,
	"auto_instal": False,
	"application": True,
}
