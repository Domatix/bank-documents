from odoo import models, fields, api, exceptions


class AccountDocumentLine(models.Model):
    _name = 'account.document.line'
    _description = 'Payment Document Lines'

    document_id = fields.Many2one(
        'account.payment.document',
        string='Payment Document',
        ondelete='cascade',
        index=True)

    company_id = fields.Many2one(
        related='document_id.company_id', store=True, readonly=True)
    company_currency_id = fields.Many2one(
        related='document_id.company_currency_id', store=True, readonly=True)
    payment_type = fields.Selection(
        related='document_id.payment_type', store=True, readonly=True)
    bank_account_required = fields.Boolean(
        related='document_id.payment_method_id.bank_account_required',
        readonly=True)
    state = fields.Selection(
        related='document_id.state', string='State',
        readonly=True, store=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency of the Payment Transaction',
        required=True,
        default=lambda self: self.env.user.company_id.currency_id)
    amount_currency = fields.Monetary(
        string="Amount", currency_field='currency_id')
    amount_company_currency = fields.Monetary(
        compute='_compute_amount_company_currency',
        string='Amount in Company Currency', readonly=True,
        currency_field='company_currency_id')
    date = fields.Date(string='Payment Date')
    move_line_id = fields.Many2one(
        'account.move.line', string='Journal Item',
        ondelete='restrict')
    ml_maturity_date = fields.Date(
        related='move_line_id.date_maturity', readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True,
        domain=[('parent_id', '=', False)])
    communication = fields.Char(
        string='Communication', required=True,
        help="Label of the payment that will be seen by the destinee")
    communication_type = fields.Selection([
        ('normal', 'Free'),
        ], string='Communication Type', required=True, default='normal')

    invoice_state = fields.Selection(
        related="move_line_id.move_id.invoice_payment_state")

    @api.depends(
        'amount_currency', 'currency_id', 'company_currency_id', 'date')
    def _compute_amount_company_currency(self):
        for line in self:
            if line.currency_id and line.company_currency_id:
                line.amount_company_currency = line.currency_id._convert(
                    line.amount_currency, line.company_currency_id,
                    line.company_id, line.date or fields.Date.today(),
                )
            else:
                line.amount_company_currency = 0

    def invoice_reference_type2communication_type(self):
        """This method is designed to be inherited by
        localization modules"""
        # key = value of 'reference_type' field on account_invoice
        # value = value of 'communication_type' field on account_payment_line
        res = {'none': 'normal', 'structured': 'structured'}
        return res

    @api.onchange('move_line_id')
    def move_line_id_change(self):
        if self.move_line_id:
            vals = self.move_line_id._prepare_document_line_vals(
                self.document_id)
            vals.pop('document_id')
            for field, value in vals.items():
                self[field] = value
        else:
            self.partner_id = False
            self.amount_currency = 0.0
            self.currency_id = self.env.user.company_id.currency_id
            self.communication = False

    def create(self, vals):
        res = super(AccountDocumentLine, self).create(vals)
        for line in res:
            if line.move_line_id and line.move_line_id.move_id.is_invoice():
                line.move_line_id.move_id.message_post(
                    body="Factura introducida en documento {}. Cantidad: {}".format(line.document_id.name, line.amount_currency)
                )
        return res

    def unlink(self):
        for line in self:
            if line.move_line_id and line.move_line_id.move_id.is_invoice():
                line.move_line_id.move_id.message_post(
                    body="Factura extraída del documento {}.".format(line.document_id.name)
                )
        return super(AccountDocumentLine, self).unlink()



    def write(self, values):
        for record in self:
            if 'amount_currency' in values and record.move_line_id and record.move_line_id.move_id.is_invoice():
                record.move_line_id.move_id.message_post(
                    body="Actualizada cantidad en documento {}. {} {} {}".format(record.document_id.name, record.amount_currency, u'\N{Rightwards Arrow with Equilateral Arrowhead}', values['amount_currency'])
                )
        return super(AccountDocumentLine, self).write(values)
