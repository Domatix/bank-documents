import base64
import json
from odoo import fields, models, api, _
from odoo.tools import float_is_zero


class AccountMove(models.Model):
    _inherit = 'account.move'


    document_line_ids = fields.One2many(
        comodel_name='account.document.line',
        compute="_compute_payment_ids",
        string="Document lines",
    )

    payment_line_ids = fields.One2many(
        comodel_name='account.payment.line',
        compute="_compute_payment_ids",
        string="Payment lines",
    )

    payment_document_id = fields.Many2one(
        'account.payment.document', string='Payment Document', copy=False,
        readonly=True)

    amount_pending_on_receivables = fields.Monetary(
        string='Amount pending on receivables',
        compute='_compute_amount_on_receivables',
        store=True,
        currency_field='company_currency_id'
    )

    def _compute_payment_ids(self):
        for record in self:
            document_lines = self.env["account.document.line"].search([("move_line_id", "in", record.line_ids.ids)])
            payment_lines = self.env["account.payment.line"].search([("move_line_id", "in", record.line_ids.ids)])
            record.document_line_ids = (document_lines)
            record.payment_line_ids = (payment_lines)

    @api.depends('payment_document_id', 'payment_order_id', 'amount_residual', 'line_ids',
                 'line_ids.amount_pending_on_receivables', 'document_line_ids', 'payment_line_ids', 'returned_payment')
    def _compute_amount_on_receivables(self):
        for record in self:
            if record.is_invoice():
                #Calculamos el signo en función de si es de cliente o de proveedor
                #Añadimos el else para los asientos que no sean facturas
                if record.type in ('in_invoice', 'out_refund'):
                    lines = record.line_ids.filtered(
                        lambda r: r.account_internal_type in ['payable', 'receivable'])
                    sign = 1
                elif record.type in ('out_invoice', 'in_refund'):
                    lines = record.line_ids.filtered(
                        lambda r: r.account_internal_type in ['payable', 'receivable'])
                    sign = -1
                else:
                    lines = self.env['account.move.line']

                #Si está pagada no puede haber cantidad pendiente sin documento
                #Si no, tenemos que comprobar qué apuntes de los conciliados están vinculados
                #a ordenes de cobro o documentos recibidos.
                #Los apuntes conciliados que no tengan nada que ver con ordenes o documentos
                #se restan del total para luego tener un total fiable que comparar con las cantidades
                #de las ordenes/documentos.
                if record.invoice_payment_state == 'paid':
                    amount = 0
                else:
                    partials = lines.mapped('matched_debit_ids') + lines.mapped(
                        'matched_credit_ids')
                    order_amount = 0
                    others_amount = 0
                    for partial in partials:
                        counterpart_lines = partial.debit_move_id + partial.credit_move_id
                        counterpart_line = counterpart_lines.filtered(lambda line: line not in record.line_ids)
                        if counterpart_line.bank_payment_line_id or counterpart_line.document_line_id:
                            order_amount += partial.amount
                        else:
                            others_amount += partial.amount
                    amount = record.amount_total_signed - others_amount * -sign

                    for line in lines:
                        if line.payment_line_ids:
                            amount += sum(line.payment_line_ids.mapped('amount_currency')) * sign
                        if line.document_line_ids:
                            amount += sum(line.document_line_ids.mapped('amount_currency')) * sign

                    if record.returned_payment:
                        returned_reconciles = self.env["account.partial.reconcile"].search(
                            [("origin_returned_move_ids.move_id", "=", record.id)]
                        )
                        for returned_reconcile in returned_reconciles:
                            amount += returned_reconcile.amount

                record.amount_pending_on_receivables = amount
            else:
                record.amount_pending_on_receivables = 0

    def _compute_payments_widget_to_reconcile_info(self):
        for move in self:
            move.invoice_outstanding_credits_debits_widget = json.dumps(False)
            move.invoice_has_outstanding = False

            if move.state != 'posted' or move.invoice_payment_state != 'not_paid' or not move.is_invoice(include_receipts=True):
                continue
            pay_term_line_ids = move.line_ids.filtered(lambda line: line.account_id.user_type_id.type in ('receivable', 'payable'))

            domain = [('account_id', 'in', pay_term_line_ids.mapped('account_id').ids),
                      '|', ('move_id.state', '=', 'posted'), '&', ('move_id.state', '=', 'draft'), ('journal_id.post_at', '=', 'bank_rec'),
                      ('partner_id', '=', move.commercial_partner_id.id),
                      ('not_reconcile', '=', False),
                      ('reconciled', '=', False), '|', ('amount_residual', '!=', 0.0),
                      ('amount_residual_currency', '!=', 0.0)]

            if move.is_inbound():
                domain.extend([('credit', '>', 0), ('debit', '=', 0)])
                type_payment = _('Outstanding credits')
            else:
                domain.extend([('credit', '=', 0), ('debit', '>', 0)])
                type_payment = _('Outstanding debits')
            info = {'title': '', 'outstanding': True, 'content': [], 'move_id': move.id}
            lines = self.env['account.move.line'].search(domain)
            currency_id = move.currency_id
            if len(lines) != 0:
                for line in lines:
                    # get the outstanding residual value in invoice currency
                    if line.currency_id and line.currency_id == move.currency_id:
                        amount_to_show = abs(line.amount_residual_currency)
                    else:
                        currency = line.company_id.currency_id
                        amount_to_show = currency._convert(abs(line.amount_residual), move.currency_id, move.company_id,
                                                           line.date or fields.Date.today())
                    if float_is_zero(amount_to_show, precision_rounding=move.currency_id.rounding):
                        continue
                    info['content'].append({
                        'journal_name': line.ref or line.move_id.name,
                        'amount': amount_to_show,
                        'currency': currency_id.symbol,
                        'id': line.id,
                        'position': currency_id.position,
                        'digits': [69, move.currency_id.decimal_places],
                        'payment_date': fields.Date.to_string(line.date),
                    })
                info['title'] = type_payment
                move.invoice_outstanding_credits_debits_widget = json.dumps(info)
                move.invoice_has_outstanding = True

    def get_account_move_as_base_64_PDF(self):
        self = self.sudo()
        content = self.env.ref('account.account_invoices').render_qweb_pdf(self.id)[0]
        return {
            'data': base64.encodebytes(content)
        }