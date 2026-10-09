# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import date, datetime, timedelta
import calendar
import base64


class WHTManagementCategory(models.Model):
    _name = 'wht.management.category'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'WHT Category'
    _rec_name = 'name'

    name = fields.Char(string="Name", tracking=True)
    account_id = fields.Many2one('account.account', string="Account", tracking=True)

    wht_line_ids = fields.One2many('wht.management', 'wht_category_id', string='WHT Rate Lines')


class WHTManagement(models.Model):
    _name = 'wht.management'
    _description = 'WHT Rate'
    _rec_name = 'name'

    name = fields.Char(string="Name")
    wht_category_id = fields.Many2one('wht.management.category', string="WHT Category")
    account_id = fields.Many2one(related='wht_category_id.account_id', store=True, string="WHT Account")

    wht_type = fields.Selection(string="Type", selection=[('percentage', 'Percentage %'), ('fixed', 'Fixed')],
                                default='percentage')

    wht_value = fields.Monetary(string='Rate', required=False)
    currency_id = fields.Many2one('res.currency', string='Currency', required=False,
                                  default=lambda self: self.env.user.company_id.currency_id)
