from odoo import fields, models, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    document_line_ids = fields.One2many(
        comodel_name='account.document.line',
        inverse_name='move_line_id',
        string="Document lines",
    )

    document_line_id = fields.Many2one(
        comodel_name='account.document.line',
        string='Transaction')

    order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Order')

    not_reconcile = fields.Boolean()

    document = fields.Boolean()

    amount_pending_on_receivables = fields.Monetary(
        string='Amount pending on receivables',
        compute='_compute_amount_on_receivables',
        store=True,
        currency_field='company_currency_id'
    )

    @api.depends('payment_line_ids', 'payment_line_ids.amount_currency', 'payment_line_ids.order_id.state',
                 'bank_payment_line_id', 'document_line_ids', 'document_line_ids.amount_currency',
                 'document_line_ids.document_id.state', 'document_line_id', 'amount_residual', 'partial_reconcile_returned_ids',
                 'move_id.returned_payment')
    def _compute_amount_on_receivables(self):
        for record in self:
            if record.move_id.is_invoice():
                sign = 0
                if record.move_id.type in ('in_invoice', 'out_refund'):
                    if record.account_internal_type in ['payable', 'receivable']:
                        sign = 1
                elif record.move_id.type in ('out_invoice', 'in_refund'):
                    if record.account_internal_type in ['payable', 'receivable']:
                        sign = -1
                if record.move_id.invoice_payment_state == 'paid':
                    amount = 0
                else:
                    partials = record.mapped('matched_debit_ids') + record.mapped(
                        'matched_credit_ids')
                    order_amount = 0
                    others_amount = 0
                    for partial in partials:
                        counterpart_lines = partial.debit_move_id + partial.credit_move_id
                        counterpart_line = counterpart_lines.filtered(lambda line: line not in record)
                        if counterpart_line.bank_payment_line_id or counterpart_line.document_line_id:
                            order_amount += partial.amount
                        else:
                            others_amount += partial.amount
                    amount = record.balance - others_amount * -sign
                    if record.payment_line_ids.filtered(lambda r: r.order_id.state != 'cancel'):
                        amount += sum(record.payment_line_ids.mapped('amount_currency')) * sign
                    if record.document_line_ids.filtered(lambda r: r.document_id.state != 'cancel'):
                        amount += sum(record.document_line_ids.mapped('amount_currency')) * sign

                    if record.move_id.returned_payment:
                        returned_reconciles = self.env["account.partial.reconcile"].search(
                            [("origin_returned_move_ids.move_id", "=", record.move_id.id)]
                        )
                        for returned_reconcile in returned_reconciles:
                            amount += returned_reconcile.amount

                record.amount_pending_on_receivables = amount
            else:
                record.amount_pending_on_receivables = 0

    def _prepare_document_line_vals(self, document):
        self.ensure_one()
        assert document, 'Missing payment document'
        aplo = self.env['account.document.line']
        # default values for communication_type and communication
        communication_type = 'normal'
        communication = self.move_id.ref or self.move_id.name
        # change these default values if move line is linked to an invoice
        if self.move_id.is_invoice():
            if self.move_id.reference_type != 'none':
                communication = self.move_id.ref
                ref2comm_type =\
                    aplo.invoice_reference_type2communication_type()
                communication_type =\
                    ref2comm_type[self.move_id.reference_type]
            else:
                if (
                        self.move_id.type in ('in_invoice', 'in_refund') and
                        self.move_id.ref
                ):
                    communication = self.move_id.ref
                elif 'out' in self.move_id.type:
                    # Force to only put invoice number here
                    communication = self.move_id.name
        if self.currency_id:
            currency_id = self.currency_id.id
            amount_currency = self.amount_residual_currency
        else:
            currency_id = self.company_id.currency_id.id
            amount_currency = self.amount_residual
            # TODO : check that self.amount_residual_currency is 0
            # in this case

        if self.move_id.is_invoice():
            if document.payment_type == 'inbound':
                if amount_currency > self.amount_pending_on_receivables:
                    amount_currency = self.amount_pending_on_receivables

            if document.payment_type == 'outbound':
                amount_currency *= -1
                if amount_currency < self.amount_pending_on_receivables:
                    amount_currency = self.amount_pending_on_receivables
        vals = {
            'document_id': document.id,
            'partner_id': self.partner_id.id,
            'move_line_id': self.id,
            'communication': communication,
            'communication_type': communication_type,
            'currency_id': currency_id,
            'amount_currency': amount_currency,
            # date is set when the user confirms the payment document
            }
        return vals

    def create_document_line_from_move_line(self, document):
        vals_list = []
        for mline in self:
            vals_list.append(mline._prepare_document_line_vals(document))
        return self.env['account.document.line'].create(vals_list)

    def _prepare_payment_line_vals(self, payment_order):
        vals = super()._prepare_payment_line_vals(payment_order)
        if "amount_currency" in vals and self.move_id.is_invoice():
            if payment_order.payment_type == 'inbound':
                if vals["amount_currency"] > self.amount_pending_on_receivables:
                    vals["amount_currency"] = self.amount_pending_on_receivables

            if payment_order.payment_type == 'outbound':
                if vals["amount_currency"] < self.amount_pending_on_receivables:
                    vals["amount_currency"] = self.amount_pending_on_receivables
        return vals


    def create_payment_line_from_move_line(self, payment_order):
        res = super().create_payment_line_from_move_line(payment_order)
        for line in self:
            if line.move_id.payment_document_id not in payment_order.payment_document_ids:
                payment_order.payment_document_ids = [(4, line.move_id.payment_document_id.id)]
        return res