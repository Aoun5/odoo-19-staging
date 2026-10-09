# -*- coding: utf-8 -*-
{
    'name': "WHT Management",

    'author': 'Trionex PVT LTD',
    'website': 'https://www.trionex.pk',

    'category': 'Account',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',

    # 'depends': ['base', 'account', 'purchase_advance_payment'],
    'depends': ['base', 'account', 'trionex_access_rights'],

    'data': [
        'security/ir.model.access.csv',

        'views/views.xml',
        'views/account_payment_register_view.xml',
        # 'views/account_voucher_purchase_view.xml',
    ],

}
