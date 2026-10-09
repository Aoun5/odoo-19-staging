{
    'name': 'Trionex POS Stock Display',
    'version': '19.0.1.9.0',
    'author': 'Ahsan',
    'category': 'Point of Sale',
    'summary': 'Show product stock in POS, restrict low stock orders, real-time qty sync via bus',
    'depends': ['point_of_sale', 'stock', 'bus'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'trionex_pos_stock/static/src/js/pos_stock_sync.js',
            'trionex_pos_stock/static/src/overrides/components/orderline/orderline.js',
            'trionex_pos_stock/static/src/overrides/components/orderline/orderline.xml',
            # 'trionex_pos_stock/static/src/overrides/components/product_card/product_card.js',
            'trionex_pos_stock/static/src/overrides/components/product_popup/product_info_popup.js',
            # 'trionex_pos_stock/static/src/overrides/components/product_card/product_card.xml',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
}
