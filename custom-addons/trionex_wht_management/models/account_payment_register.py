from collections import defaultdict
from datetime import datetime, timedelta

from odoo import models, fields, _, Command
from odoo.exceptions import ValidationError

from odoo import api
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    line_ids = fields.Many2many(
        'account.move.line',
        'account_payment_register_move_line_rel',
        'wizard_id', 'line_id',
        string="Journal items", readonly=True, copy=False, required=False
    )

    is_apply_wht = fields.Boolean(string="Apply WHT")
    wht_line_ids = fields.One2many('payment.register.wht.lines', 'payment_reg_id', string='WHT Lines')

    total_wht_amount = fields.Monetary(string='WHT Amount', required=False, compute='compute_total_amounts', store=True)
    total_bank_amount = fields.Monetary(string='Bank Amount', required=False, store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=False,
                                  default=lambda self: self.env.user.company_id.currency_id)

    type_payment = fields.Selection(string="Amount Type", selection=[('fixed', 'Fixed'), ('percent', 'Percent (%)')],
                                    required=False, default='fixed')

    payment_value = fields.Float(string="Payment Value", required=False, )
    due_amount = fields.Float(string="Due Value", required=False, compute='_compute_due_amount', store=True)

    cheque_id = fields.Char(string="Payment ID", required=False)

    wht_grouped_data = fields.Text(string='WHT Category Summary', compute='_compute_wht_grouped_data', store=True)

    @api.depends('wht_line_ids', 'wht_line_ids.wht_value', 'wht_line_ids.wht_type', 'amount')
    def _compute_wht_grouped_data(self):
        for rec in self:
            data = {}
            base_amount = rec.amount or 0.0

            for line in rec.wht_line_ids:
                category = line.wht_category_id.name or 'Unknown'
                if line.wht_type == 'percentage':
                    wht_amt = (base_amount * (line.wht_value or 0.0)) / 100
                else:
                    wht_amt = line.wht_value or 0.0

                data[category] = data.get(category, 0) + wht_amt

            summary_lines = [f"{cat}: Rs {val:,.2f}" for cat, val in data.items()]
            rec.wht_grouped_data = '\n'.join(summary_lines)

    @api.depends('can_edit_wizard', 'source_amount', 'source_amount_currency', 'source_currency_id', 'company_id',
                 'currency_id', 'payment_date')
    def _compute_due_amount(self):
        # NOTE: previously used wizard._get_batches()[0] + _get_total_amount_in_wizard_currency_to_full_reconcile(),
        # both private helpers that no longer exist on account.payment.register in v19. Replaced with the same
        # calculation done directly from the stable public fields (source_amount_currency/source_currency_id),
        # converting to the wizard's payment currency the same way the core helper used to.
        for wizard in self:
            if not wizard.journal_id or not wizard.currency_id or not wizard.payment_date:
                wizard.due_amount = wizard.due_amount
                # wizard.payment_value = wizard.due_amount
            elif wizard.source_currency_id and wizard.can_edit_wizard:
                if wizard.source_currency_id == wizard.currency_id:
                    wizard.due_amount = wizard.source_amount_currency
                else:
                    wizard.due_amount = wizard.source_currency_id._convert(
                        wizard.source_amount_currency, wizard.currency_id, wizard.company_id, wizard.payment_date)
                # wizard.payment_value = wizard.due_amount
            else:
                wizard.due_amount = None
                # wizard.payment_value = None

    @api.onchange('type_payment')
    def _onchange_type_payment(self):
        for rec in self:
            if rec.type_payment == 'fixed':
                rec.payment_value = rec.due_amount
                rec.amount = rec.due_amount

            elif rec.type_payment == 'percent':
                rec.payment_value = 0.0
                rec.amount = 0.0

    @api.onchange('type_payment', 'payment_value', 'journal_id', 'is_apply_wht', 'payment_date')
    def onchange_payment_value(self):
        for rec in self:
            if rec.type_payment == 'fixed':
                if rec.payment_value > rec.due_amount:
                    raise ValidationError(_('Amount cannot exceed the due amount (%.2f).') % rec.due_amount)
                rec.amount = rec.payment_value

            elif rec.type_payment == 'percent':
                if rec.payment_value > 100:
                    raise ValidationError(_('Percentage value cannot exceed 100%.'))
                rec.amount = (rec.due_amount * rec.payment_value) / 100

    @api.onchange('is_apply_wht')
    def onchange_is_apply_wht(self):
        for rec in self:
            if not rec.is_apply_wht:
                rec.wht_line_ids = [(5, 0, 0)]

    @api.depends('wht_line_ids', 'wht_line_ids.wht_value', 'wht_line_ids.wht_type', 'amount', 'type_payment',
                 'payment_value', 'journal_id', 'payment_date')
    def compute_total_amounts(self):
        for rec in self:

            wht_amt = 0
            base_amount = rec.amount or 0.0

            for line in rec.wht_line_ids:
                if line.wht_type == 'percentage':
                    wht_amt = (base_amount * (line.wht_value or 0.0)) / 100
                else:
                    wht_amt = line.wht_value or 0.0

            if rec.wht_line_ids:
                # rec.total_wht_amount = sum(rec.wht_line_ids.mapped('wht_amount'))
                rec.total_wht_amount = wht_amt
                rec.total_bank_amount = rec.amount - rec.total_wht_amount
            else:
                rec.total_wht_amount = 0
                rec.total_bank_amount = rec.amount

    @api.onchange('wht_line_ids.wht_value', 'amount')
    def onchange_wht_type(self):
        for rec in self:
            if rec.wht_line_ids:
                for line in rec.wht_line_ids:
                    amount = rec.amount or 0.0
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

                if total_amount > rec.amount:
                    raise ValidationError(_('Total WHT amount (%.2f) cannot exceed the payment amount (%.2f).') % (
                        total_amount, rec.amount))

    def _create_payment_vals_from_wizard(self, batch_result):
        res = super(AccountPaymentRegister, self)._create_payment_vals_from_wizard(batch_result)
        wht_lines_data = [(0, 0, {
            'wht_category_id': line.wht_category_id.id,
            'wht_id': line.wht_id.id,
            'wht_account_id': line.wht_account_id.id,
            'wht_value': line.wht_value,
            'wht_amount': line.wht_amount,
        }) for line in self.wht_line_ids]

        if self._context.get('active_model') == 'account.move':
            lines = self.env['account.move'].browse(self._context.get('active_ids', [])).line_ids
            move = lines.mapped('id')
            # print("Move ------------------ ", move.name)

        elif self._context.get('active_model') == 'account.move.line':
            lines = self.env['account.move.line'].browse(self._context.get('active_ids', []))
            move = lines.mapped('move_id')
            # print("Move Lines Wala ------------------ ", move.name)
            res.update({
                'invoice_no': move.name,
            })

        else:
            raise UserError(_(
                "The register payment wizard should only be called on account.move or account.move.line records."
            ))

        res.update({
            'amount': self.amount,
            'cheque_id': self.cheque_id,
            'is_apply_wht': self.is_apply_wht,
            'payment_wht_line_ids': wht_lines_data,
        })

        return res

    def action_create_payments(self):
        for rec in self:
            if rec.amount == 0 or rec.payment_value == 0:
                raise ValidationError(_('Amount cannot be zero.'))
        return super(AccountPaymentRegister, self).action_create_payments()


class AccountPaymentRegisterWHTLine(models.TransientModel):
    _name = 'payment.register.wht.lines'
    _description = 'Account Payment Register WHT Line'

    # NOTE: 'advance_payment_reg_id' (Many2one to 'account.voucher.wizard.purchase') was removed.
    # That model belongs to the 'purchase_advance_payment' module, which is not part of this
    # module's dependencies (see __manifest__.py) and whose related view/model files are disabled.
    # Keeping the field here made the module fail to install with an unknown comodel error.
    # If 'purchase_advance_payment' is added back as a dependency, re-add this field and re-enable
    # models/account_voucher_purchase.py + views/account_voucher_purchase_view.xml.

    payment_reg_id = fields.Many2one('account.payment.register', string='Payment Register', required=False,
                                     ondelete='cascade')

    # account_payment_id = fields.Many2one('account.payment', string='Account Payment', required=False)

    wht_category_id = fields.Many2one('wht.management.category', string="WHT Category")

    wht_id = fields.Many2one('wht.management', string='WHT', required=False)
    wht_name = fields.Char(related='wht_id.name', string='WHT Name', readonly=True)
    wht_account_id = fields.Many2one(related='wht_id.account_id', store=True, readonly=True)
    wht_type = fields.Selection(related='wht_id.wht_type', store=True, readonly=True)

    wht_value = fields.Monetary(related='wht_id.wht_value', store=True, readonly=True)
    wht_amount = fields.Monetary(string='Amount', required=False)
    currency_id = fields.Many2one('res.currency', string='Currency', required=False,
                                  default=lambda self: self.env.user.company_id.currency_id)

    @api.onchange('wht_value')
    def onchange_wht_type(self):
        amount = total_amount = 0
        for line in self:
            if line.payment_reg_id:
                amount = line.payment_reg_id.amount or 0.0
                total_amount = sum(l.wht_amount for l in line.payment_reg_id.wht_line_ids if l.wht_amount)

            value = line.wht_value or 0.0

            if line.wht_type == 'percentage':
                if value >= 100:
                    raise ValidationError(_('WHT Percentage cannot be 100% or more.'))
                line.wht_amount = (amount * value) / 100

            elif line.wht_type == 'fixed':
                if value >= amount:
                    raise ValidationError(_('WHT amount cannot exceed or equal total amount (%.2f).') % amount)
                line.wht_amount = value

            if total_amount > amount:
                raise ValidationError(_('Total WHT amount (%.2f) cannot exceed the payment amount (%.2f).') % (
                    total_amount, amount))


class AccountPaymentsRegisterWHTLines(models.Model):
    _name = 'payments.register.wht.lines'
    _description = 'Account Payment Register WHT Line'

    account_payment_id = fields.Many2one('account.payment', string='Account Payment', required=False)

    wht_category_id = fields.Many2one('wht.management.category', string="WHT Category")

    wht_id = fields.Many2one('wht.management', string='WHT', required=False)
    wht_name = fields.Char(related='wht_id.name', string='WHT Name', readonly=True)
    wht_account_id = fields.Many2one(related='wht_id.account_id', store=True, readonly=True)
    wht_type = fields.Selection(related='wht_id.wht_type', store=True, readonly=True)

    wht_value = fields.Monetary(related='wht_id.wht_value', store=True, readonly=True)
    wht_amount = fields.Monetary(string='Amount', required=False)
    currency_id = fields.Many2one('res.currency', string='Currency', required=False,
                                  default=lambda self: self.env.user.company_id.currency_id)

    @api.onchange('wht_value')
    def onchange_wht_type(self):
        amount = total_amount = 0
        for line in self:
            if line.account_payment_id:
                amount = line.account_payment_id.amount or 0.0
                total_amount = sum(l.wht_amount for l in line.account_payment_id.payment_wht_line_ids if l.wht_amount)

            value = line.wht_value or 0.0

            if line.wht_type == 'percentage':
                if value >= 100:
                    raise ValidationError(_('WHT Percentage cannot be 100% or more.'))
                line.wht_amount = (amount * value) / 100

            elif line.wht_type == 'fixed':
                if value >= amount:
                    raise ValidationError(_('WHT amount cannot exceed or equal total amount (%.2f).') % amount)
                line.wht_amount = value

            if total_amount > amount:
                raise ValidationError(_('Total WHT amount (%.2f) cannot exceed the payment amount (%.2f).') % (
                    total_amount, amount))


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_apply_wht = fields.Boolean(string="Apply WHT")

    payment_wht_line_ids = fields.One2many(
        comodel_name='payments.register.wht.lines',
        inverse_name='account_payment_id',
        string='WHT Lines')

    cheque_id = fields.Char(string="Payment ID", required=False)
    invoice_no = fields.Char(string="Invoice No", required=False)

    total_wht_amount = fields.Monetary(string='WHT Amount', required=False, compute='compute_total_amounts', store=True)
    total_bank_amount = fields.Monetary(string='Bank Amount', required=False,  store=True)

    wht_grouped_data = fields.Text(string='WHT Category Summary', compute='_compute_wht_grouped_data', store=True)

    @api.depends('payment_wht_line_ids', 'payment_wht_line_ids.wht_value', 'payment_wht_line_ids.wht_type', 'amount')
    def _compute_wht_grouped_data(self):
        for rec in self:
            data = {}
            base_amount = rec.amount or 0.0

            for line in rec.payment_wht_line_ids:
                category = line.wht_category_id.name or 'Unknown'
                if line.wht_type == 'percentage':
                    wht_amt = (base_amount * (line.wht_value or 0.0)) / 100
                else:
                    wht_amt = line.wht_value or 0.0

                data[category] = data.get(category, 0) + wht_amt

            summary_lines = [f"{cat}: Rs {val:,.2f}" for cat, val in data.items()]
            rec.wht_grouped_data = '\n'.join(summary_lines)

    # @api.depends('payment_wht_line_ids.wht_value', 'amount')
    @api.depends('payment_wht_line_ids', 'payment_wht_line_ids.wht_value', 'payment_wht_line_ids.wht_type', 'amount')
    def compute_total_amounts(self):
        for rec in self:
            if rec.payment_wht_line_ids:
                rec.total_wht_amount = sum(rec.payment_wht_line_ids.mapped('wht_amount'))
                rec.total_bank_amount = rec.amount - rec.total_wht_amount
            else:
                rec.total_wht_amount = 0
                rec.total_bank_amount = rec.amount

    is_test = fields.Boolean(string="Test")

    def create(self, vals):
        if isinstance(vals, list):
            for val in vals:
                val['is_test'] = True
        else:
            vals['is_test'] = True

        res = super(AccountPayment, self).create(vals)
        return res

    def compute_is_test(self):
        for rec in self:
            rec.is_test = True

    def action_post(self):
        for rec in self:
            if rec.move_id and rec.move_id.state == 'draft':
                print("Move Id ----------------- ", rec.move_id.name)
                rec.move_id.line_ids.unlink()

            move_vals = {
                'line_ids': [(5, 0, 0)] + [
                    (0, 0, vals) for vals in rec._prepare_move_line_default_vals()
                ]
            }
            rec.move_id.with_context(skip_account_move_synchronization=True).write(move_vals)

            # rec._compute_amount_company_currency_signed()

        return super(AccountPayment, self).action_post()

    def compute_wht_entries(self):
        for rec in self:
            if rec.move_id:
                rec.move_id.line_ids.unlink()

                move_vals = {
                    'line_ids': [(5, 0, 0)] + [
                        (0, 0, vals) for vals in rec._prepare_move_line_default_vals()
                    ]
                }
                rec.move_id.with_context(skip_account_move_synchronization=True).write(move_vals)

    @api.onchange('payment_wht_line_ids.wht_value', 'amount')
    def onchange_wht_type(self):
        for rec in self:
            if rec.payment_wht_line_ids:
                for line in rec.payment_wht_line_ids:
                    amount = rec.amount or 0.0
                    value = line.wht_value or 0.0

                    if line.wht_type == 'percentage':
                        if value >= 100:
                            raise ValidationError(_('WHT Percentage cannot be 100% or more.'))
                        line.wht_amount = (amount * value) / 100

                    elif line.wht_type == 'fixed':
                        if value >= amount:
                            raise ValidationError(_('WHT amount cannot exceed or equal total amount (%.2f).') % amount)
                        line.wht_amount = value

                total_amount = sum(rec.payment_wht_line_ids.mapped('wht_amount'))

                if total_amount > rec.amount:
                    raise ValidationError(_('Total WHT amount (%.2f) cannot exceed the payment amount (%.2f).') % (
                        total_amount, rec.amount))

    # NOTE: '_compute_amount_company_currency_signed' override was removed. It re-declared
    # @api.depends('amount_total_signed', 'payment_type') to override the core compute of
    # 'amount_company_currency_signed' on account.payment, but 'amount_total_signed' is not a
    # field on account.payment (it doesn't exist in v19), which broke the field's dependency
    # graph and crashed on any account.payment write. The WHT amounts are already correctly
    # reflected in the journal entry lines via _prepare_move_line_default_vals below, so this
    # override wasn't needed for WHT accounting to work correctly.

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        write_off_line_vals = write_off_line_vals or {}
        result = []

        for rec in self:
            if not rec.is_apply_wht or not rec.payment_wht_line_ids:
                result.extend(
                    super(AccountPayment, rec)._prepare_move_line_default_vals(
                        write_off_line_vals=write_off_line_vals, force_balance=force_balance
                    )
                )
                continue

            if not rec.outstanding_account_id:
                raise UserError(_(
                    "You can't create a new payment without an outstanding payments/receipts account set either on the company or the %s payment method in the %s journal.",
                    rec.payment_method_line_id.name, rec.journal_id.display_name,
                ))

            currency_id = rec.currency_id.id
            write_off_line_vals_list = write_off_line_vals or []
            line_vals_list = []

            preserved_cp = rec.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
            )[:1]
            if preserved_cp:
                account = preserved_cp.account_id.id
            else:
                if rec.partner_type == 'customer':
                    account = (rec.partner_id.property_account_receivable_id.id
                               if rec.partner_id else rec.company_id.partner_id.property_account_receivable_id.id)
                else:
                    account = (rec.partner_id.property_account_payable_id.id
                               if rec.partner_id else rec.company_id.partner_id.property_account_payable_id.id)

            total_wht = sum(rec.payment_wht_line_ids.mapped('wht_amount')) or 0.0
            net_amount = rec.amount - total_wht

            payment_type_string = "Bank Payment - " if rec.journal_id.type == 'bank' else "Cash Payment -"
            payment_id_string = f"Payment ID ({rec.cheque_id}) - " if rec.cheque_id else ""
            invoice_no_string = f"{rec.invoice_no} - " if rec.invoice_no else f"{rec.ref} - "

            for wht in rec.payment_wht_line_ids:
                line_vals_list.append({
                    'date_maturity': rec.date,
                    'currency_id': currency_id,
                    'account_id': wht.wht_account_id.id,
                    'name': (
                        f"With {wht.wht_category_id.name} - {wht.wht_id.name} WHT Payment - "
                        f"{wht.wht_amount:.2f} - "
                        f"{(rec.partner_id.name + ' - ') if rec.partner_id else ''}{invoice_no_string}{rec.date}"
                    ),
                    'partner_id': rec.partner_id.id,
                    'debit': wht.wht_amount if rec.payment_type == 'inbound' else 0.0,
                    'credit': 0.0 if rec.payment_type == 'inbound' else wht.wht_amount,
                })
                line_vals_list.append({
                    'date_maturity': rec.date,
                    'currency_id': currency_id,
                    'account_id': account,
                    'name': (
                        f"With {wht.wht_category_id.name} - {wht.wht_id.name} WHT Payment - "
                        f"{wht.wht_amount:.2f} - "
                        f"{(rec.partner_id.name + ' - ') if rec.partner_id else ''}{invoice_no_string}{rec.date}"
                    ),
                    'partner_id': rec.partner_id.id,
                    'debit': 0.0 if rec.payment_type == 'inbound' else wht.wht_amount,
                    'credit': wht.wht_amount if rec.payment_type == 'inbound' else 0.0,
                })

            line_vals_list.append({
                'date_maturity': rec.date,
                'currency_id': currency_id,
                'account_id': rec.outstanding_account_id.id,
                'name': (
                    f"{payment_type_string}"
                    f"{(rec.partner_id.name + ' - ') if rec.partner_id else ''}"
                    f"{invoice_no_string}{payment_id_string}{rec.date}"
                ),
                'partner_id': rec.partner_id.id,
                'debit': net_amount if rec.payment_type == 'inbound' else 0.0,
                'credit': 0.0 if rec.payment_type == 'inbound' else net_amount,
            })

            line_vals_list.append({
                'date_maturity': rec.date,
                'currency_id': currency_id,
                'account_id': account,
                'name': (
                    f"{payment_type_string}"
                    f"{(rec.partner_id.name + ' - ') if rec.partner_id else ''}"
                    f"{invoice_no_string}{payment_id_string}{rec.date}"
                ),
                'partner_id': rec.partner_id.id,
                'debit': 0.0 if rec.payment_type == 'inbound' else net_amount,
                'credit': net_amount if rec.payment_type == 'inbound' else 0.0,
            })

            line_vals_list += write_off_line_vals_list
            result.extend(line_vals_list)

        return result

    # NOTE: an override of '_synchronize_from_moves' used to live here. That method doesn't
    # exist on 'account.payment' in v19 (it was moved to 'account.bank.statement.line' — see
    # addons/account/models/account_bank_statement_line.py), so the override was never called by
    # anything. Removed as dead code.

    def _synchronize_to_moves(self, changed_fields):
        # NOTE: rewritten for v19. The previous version indexed the result of
        # _prepare_move_line_default_vals() as [liquidity_line, counterpart_line, *write_offs],
        # but when WHT lines are present that method returns [wht_line, payable_line, ...] first,
        # so the old code updated the wrong journal items with the wrong account/amount. It also
        # built Command.update()/Command.create() tuples that were never used (discarded, not
        # appended anywhere) — the move write() only ever touched write-off lines in practice.
        # Instead of trying to patch specific lines by position, wipe and rebuild line_ids from
        # _prepare_move_line_default_vals(), the same pattern already used by action_post() and
        # compute_wht_entries() below for this model.
        if self._context.get('skip_account_move_synchronization'):
            return

        if not any(field_name in changed_fields for field_name in self._get_trigger_fields_to_synchronize()):
            return

        for pay in self.with_context(skip_account_move_synchronization=True):
            if pay.move_id.state == 'posted':
                continue

            if 'journal_id' in changed_fields and pay.journal_id.type not in ('bank', 'cash'):
                raise UserError(_("A payment must always belong to a bank or cash journal."))

            line_vals_list = pay._prepare_move_line_default_vals()

            move_vals_to_write = {
                'partner_id': pay.partner_id.id,
                'currency_id': pay.currency_id.id,
                'partner_bank_id': pay.partner_bank_id.id,
                'line_ids': [Command.clear()] + [Command.create(vals) for vals in line_vals_list],
            }
            if 'journal_id' in changed_fields:
                move_vals_to_write.update({
                    'name': '/',
                    'journal_id': pay.journal_id.id,
                })

            pay.move_id.with_context(skip_invoice_sync=True).write(move_vals_to_write)
