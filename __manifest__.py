# -*- coding: utf-8 -*-

{
    'name': 'Mining Production',
    'version': '1.0',
    'author': 'Technoindo.com',
    'category': 'Mining',
    'depends': [
        'shipping',
        'sale_qaqc',
        'fleet',
        'stock',
    ],
    'data': [
        'views/menu.xml',
        "views/ritase_order.xml",
        "views/dumptruck_activity.xml",
        "views/stock_views.xml",

        "data/ritase_data.xml",
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
