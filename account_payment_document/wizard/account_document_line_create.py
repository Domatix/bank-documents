from odoo import models, fields, api, _


class AccountDocumentLineCreate(models.TransientModel):
    _name = 'account.document.line.create'
    _description = 'Wizard to create document lines'

    document_id = fields.Many2one(
        'account.payment.document', string='Payment Document')
    journal_ids = fields.Many2many(
        'account.journal', string='Journals Filter')
    partner_ids = fields.Many2many(
        'res.partner', string='Partners', domain=[('parent_id', '=', False)])
    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all', 'All Entries'),
    ], string='Target Moves')
    allow_blocked = fields.Boolean(
        string='Allow Litigation Move Lines')
    invoice = fields.Boolean(
        string='Linked to an Invoice or Refund')
    date_type = fields.Selection([
        ('due', 'Due Date'),
        ('move', 'Move Date'),
    ], string="Type of Date Filter", required=True)
    due_date = fields.Date(string="Due Date")
    move_date = fields.Date(
        string='Move Date', default=fields.Date.context_today)
    payment_mode = fields.Selection([
        ('same', 'Same'),
        ('same_or_null', 'Same or Empty'),
        ('any', 'Any'),
    ], string='Payment Mode')
    move_line_ids = fields.Many2many(
        'account.move.line', string='Move Lines')

    @api.model
    def default_get(self, field_list):
        res = super(AccountDocumentLineCreate, self).default_get(field_list)
        context = self.env.context
        assert context.get('active_model') == 'account.payment.document', \
            'active_model should be payment.document'
        assert context.get('active_id'), 'Missing active_id in context !'
        document = self.env['account.payment.document'].browse(context['active_id'])
        mode = document.payment_mode_id
        res.update({
            'journal_ids': mode.default_journal_ids.ids or False,
            'target_move': mode.default_target_move,
            'invoice': mode.default_invoice,
            'date_type': mode.default_date_type,
            'payment_mode': mode.default_payment_mode,
            'document_id': document.id,
        })
        return res

    def _prepare_move_line_domain(self):
        self.ensure_one()
        domain = [('reconciled', '=', False), ('order_id', '=', False),
                  ('company_id', '=', self.document_id.company_id.id)]
        if self.journal_ids:
            domain += [('journal_id', 'in', self.journal_ids.ids)]
        if self.partner_ids:
            domain += [('partner_id', 'in', self.partner_ids.ids)]
        if self.target_move == 'posted':
            domain += [('move_id.state', '=', 'posted')]
        if not self.allow_blocked:
            domain += [('blocked', '!=', True)]
        if self.date_type == 'due':
            domain += [
                '|',
                ('date_maturity', '<=', self.due_date),
                ('date_maturity', '=', False)]
        elif self.date_type == 'move':
            domain.append(('date', '<=', self.move_date))
        if self.invoice:
            domain.append(
                (
                    "move_id.type",
                    "in",
                    ("in_invoice", "out_invoice", "in_refund", "out_refund"),
                )
            )
        if self.payment_mode:
            if self.payment_mode == 'same':
                domain.append(
                    ('payment_mode_id', '=', self.document_id.payment_mode_id.id))
            elif self.payment_mode == 'same_or_null':
                domain += [
                    '|',
                    ('payment_mode_id', '=', False),
                    ('payment_mode_id', '=', self.document_id.payment_mode_id.id)]

        if self.document_id.payment_type == 'outbound':
            # For payables, propose all unreconciled credit lines,
            # including partially reconciled ones.
            # If they are partially reconciled with a supplier refund,
            # the residual will be added to the payment document.
            #
            # For receivables, propose all unreconciled credit lines.
            # (ie customer refunds): they can be refunded with a payment.
            # Do not propose partially reconciled credit lines,
            # as they are deducted from a customer invoice, and
            # will not be refunded with a payment.
            domain += [
                ('credit', '>', 0),
                ('account_id.internal_type', 'in', ['payable', 'receivable'])]
        elif self.document_id.payment_type == 'inbound':
            domain += [
                ('debit', '>', 0),
                ('account_id.internal_type', 'in', ['receivable', 'payable'])]

        paylines = self.env['account.document.line'].search([
            ('state', 'in', ('draft', 'open', 'advanced')),
            ('move_line_id', '!=', False)])
        if paylines:
            # Si es un documento de cobro, permitimos poder volver a seleccionar facturas a las que le quede cantidad
            # pendiente sin documento
            if self.document_id.payment_type == 'inbound':
                move_lines_ids = [payline.move_line_id.id for payline in paylines.filtered(lambda r: r.move_line_id.account_internal_type == 'receivable') if payline.move_line_id.amount_pending_on_receivables <= 0]
                move_lines_ids += [payline.move_line_id.id for payline in paylines.filtered(lambda r: r.move_line_id.account_internal_type != 'receivable')]
            else:
                move_lines_ids = [payline.move_line_id.id for payline in paylines]
            domain += [('id', 'not in', move_lines_ids)]

        paylines = self.env['account.payment.line'].search([
            ('state', 'in', ('draft', 'open', 'generated', 'uploaded')),
            ('move_line_id', '!=', False)])
        if paylines:
            if self.document_id.payment_type == 'inbound':
                move_lines_ids = [payline.move_line_id.id for payline in paylines.filtered(lambda r: r.move_line_id.account_internal_type == 'receivable') if payline.move_line_id.amount_pending_on_receivables <= 0]
                move_lines_ids += [payline.move_line_id.id for payline in paylines.filtered(lambda r: r.move_line_id.account_internal_type != 'receivable')]
            else:
                move_lines_ids = [payline.move_line_id.id for payline in paylines]
            domain += [('id', 'not in', move_lines_ids)]

        domain += [('order_id', '=', False)]

        return domain

    def populate(self):
        domain = self._prepare_move_line_domain()
        lines = self.env['account.move.line'].search(domain)
        self.move_line_ids = lines
        action = {
            'name': _('Select Move Lines to Create Transactions'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.document.line.create',
            'view_mode': 'form',
            'target': 'new',
            'res_id': self.id,
            'context': self._context,
        }
        return action

    @api.onchange(
        'date_type', 'move_date', 'due_date', 'journal_ids', 'invoice',
        'target_move', 'allow_blocked', 'payment_mode', 'partner_ids')
    def move_line_filters_change(self):
        domain = self._prepare_move_line_domain()
        res = {'domain': {'move_line_ids': domain}}
        return res

    def create_document_lines(self):
        if self.move_line_ids:
            self.move_line_ids.create_document_line_from_move_line(
                self.document_id)
        return True
