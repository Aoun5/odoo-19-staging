from collections import defaultdict
from datetime import datetime, timedelta

from odoo import models, fields, _
from odoo.exceptions import ValidationError

from odoo import api
from odoo.exceptions import UserError


class AccountVoucherPurchase(models.TransientModel):
    _inherit = 'account.voucher.wizard.purchase'

    # NOTE: this whole model is currently disabled (see models/__init__.py) because it depends on
    # 'purchase_advance_payment', which is not in this module's manifest dependencies.
    # 'advance_payment_reg_id' was removed from 'payment.register.wht.lines' (see
    # models/account_payment_register.py) since its comodel wasn't available. If you re-enable this
    # file, first add 'purchase_advance_payment' to __manifest__.py depends, then re-add
    # advance_payment_reg_id = fields.Many2one('account.voucher.wizard.purchase', ...) there.
    is_apply_wht = fields.Boolean(string="Apply WHT")
    wht_line_ids = fields.One2many('payment.register.wht.lines', 'advance_payment_reg_id', string='WHT Lines')

    total_wht_amount = fields.Monetary(string='WHT Amount', required=False, compute='compute_total_amounts')
    total_bank_amount = fields.Monetary(string='Bank Amount', required=False)
    currency_id = fields.Many2one('res.currency', string='Currency', required=False,
                                  default=lambda self: self.env.user.company_id.currency_id)

    cheque_id = fields.Char(string="Payment ID", required=False)

    wht_grouped_data = fields.Text(string='WHT Category Summary', compute='_compute_wht_grouped_data')

    type_payment = fields.Selection(string="Amount Type", selection=[('fixed', 'Fixed'), ('percent', 'Percent (%)')],
                                    required=False, default='fixed')

    payment_value = fields.Float(string="Payment Value", required=False, )

    @api.onchange('type_payment')
    def _onchange_type_payment(self):
        for rec in self:
            rec.payment_value = 0.0

    @api.onchange('type_payment', 'payment_value')
    def onchange_payment_value(self):
        for rec in self:
            rec.amount_advance = rec.amount_total
            if rec.type_payment == 'fixed':
                if rec.payment_value > rec.amount_total:
                    raise ValidationError(_('Amount cannot exceed the due amount (%.2f).') % rec.amount_total)
                rec.amount_advance = rec.payment_value

            elif rec.type_payment == 'percent':
                if rec.payment_value > 100:
                    raise ValidationError(_('Percentage value cannot exceed 100%.'))
                rec.amount_advance = (rec.amount_total * rec.payment_value) / 100

    @api.depends('wht_line_ids.wht_value', 'amount_advance')
    def _compute_wht_grouped_data(self):
        for rec in self:
            data = {}
            for line in rec.wht_line_ids:
                category = line.wht_category_id.name or 'Unknown'
                data[category] = data.get(category, 0) + line.wht_amount

            summary_lines = []
            for key, val in data.items():
                summary_lines.append(f"{key}: Rs {val:,.2f}")
            rec.wht_grouped_data = '\n'.join(summary_lines)

    @api.onchange('is_apply_wht')
    def onchange_is_apply_wht(self):
        for rec in self:
            if not rec.is_apply_wht:
                rec.wht_line_ids = [(5, 0, 0)]

    @api.depends('wht_line_ids.wht_value', 'amount_advance')
    def compute_total_amounts(self):
        for rec in self:
            if rec.wht_line_ids:
                rec.total_wht_amount = sum(rec.wht_line_ids.mapped('wht_amount'))
                rec.total_bank_amount = rec.amount_advance - rec.total_wht_amount
            else:
                rec.total_wht_amount = 0
                rec.total_bank_amount = rec.amount_advance

    @api.onchange('wht_line_ids.wht_value', 'amount_advance')
    def onchange_wht_type(self):
        for rec in self:
            if rec.wht_line_ids:
                for line in rec.wht_line_ids:
                    amount = rec.amount_advance or 0.0
                    value = line.wht_value or 0.0

                    if line.wht_type == 'percentage':
                        if value >= 100:
                            raise ValidationError(_('WHT Percentage cannot be 100% or more.'))
                        line.wht_amount = (amount * value) / 100

                    elif line.wht_type == 'fixed':
                        if value >= amount:
                            raise ValidationError(_('WHT amount cannot exceed or equal total amount (%.2f).') % amount)
                        line.wht_amount = value

                total_amount = sum(rec.wht_line_ids.mapped('wht_amount'))

                if total_amount > rec.amount_advance:
                    raise ValidationError(_('Total WHT amount (%.2f) cannot exceed the payment amount (%.2f).') % (
                        total_amount, rec.amount))

    def _prepare_payment_vals(self, purchase):
        res = super(AccountVoucherPurchase, self)._prepare_payment_vals(purchase)
        wht_lines_data = [(0, 0, {
            'wht_category_id': line.wht_category_id.id,
            'wht_id': line.wht_id.id,
            'wht_account_id': line.wht_account_id.id,
            'wht_value': line.wht_value,
            'wht_amount': line.wht_amount,
        }) for line in self.wht_line_ids]

        res.update({
            'cheque_id': self.cheque_id,
            'is_apply_wht': self.is_apply_wht,
            'payment_wht_line_ids': wht_lines_data,
        })
        return res

    def make_advance_payments(self):
        res = super(AccountVoucherPurchase, self).make_advance_payments()
        for rec in self:
            if rec.amount_advance == 0:
                raise ValidationError(_('Amount cannot be zero.'))
        return res
