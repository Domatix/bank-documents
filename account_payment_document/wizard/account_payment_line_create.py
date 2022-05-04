from odoo import models, fields, api, _


class AccountPaymentLineCreate(models.TransientModel):
    _inherit = 'account.payment.line.create'

    def _prepare_move_line_domain(self):
        # domain = super(AccountPaymentLineCreate, self)._prepare_move_line_domain()
        self.ensure_one()
        domain = [
            ("reconciled", "=", False),
            ("company_id", "=", self.order_id.company_id.id),
        ]
        if self.journal_ids:
            domain += [("journal_id", "in", self.journal_ids.ids)]
        if self.partner_ids:
            domain += [("partner_id", "in", self.partner_ids.ids)]
        if self.target_move == "posted":
            domain += [("move_id.state", "=", "posted")]
        if not self.allow_blocked:
            domain += [("blocked", "!=", True)]
        if self.date_type == "due":
            domain += [
                "|",
                ("date_maturity", "<=", self.due_date),
                ("date_maturity", "=", False),
            ]
        elif self.date_type == "move":
            domain.append(("date", "<=", self.move_date))
        if self.invoice:
            domain.append(
                (
                    "move_id.type",
                    "in",
                    ("in_invoice", "out_invoice", "in_refund", "out_refund"),
                )
            )
        if self.payment_mode:
            if self.payment_mode == "same":
                domain.append(
                    ("payment_mode_id", "=", self.order_id.payment_mode_id.id)
                )
            elif self.payment_mode == "same_or_null":
                domain += [
                    "|",
                    ("payment_mode_id", "=", False),
                    ("payment_mode_id", "=", self.order_id.payment_mode_id.id),
                ]

        if self.order_id.payment_type == "outbound":
            # For payables, propose all unreconciled credit lines,
            # including partially reconciled ones.
            # If they are partially reconciled with a supplier refund,
            # the residual will be added to the payment order.
            #
            # For receivables, propose all unreconciled credit lines.
            # (ie customer refunds): they can be refunded with a payment.
            # Do not propose partially reconciled credit lines,
            # as they are deducted from a customer invoice, and
            # will not be refunded with a payment.
            domain += [
                ("credit", ">", 0),
                ("account_id.internal_type", "in", ["payable", "receivable"]),
            ]
        elif self.order_id.payment_type == "inbound":
            domain += [
                ("debit", ">", 0),
                ("account_id.internal_type", "in", ["receivable", "payable"]),
            ]

        paylines = self.env['account.payment.line'].search([
            ('state', 'in', ('draft', 'open', 'generated', 'uploaded')),
            ('move_line_id', '!=', False)])
        if paylines:
            if self.order_id.payment_type == 'inbound':
                move_lines_ids = [payline.move_line_id.id for payline in
                                  paylines.filtered(lambda r: r.move_line_id.account_internal_type == 'receivable') if
                                  payline.move_line_id.amount_pending_on_receivables <= 0]
                move_lines_ids += [payline.move_line_id.id for payline in
                                   paylines.filtered(lambda r: r.move_line_id.account_internal_type != 'receivable')]
            else:
                move_lines_ids = [payline.move_line_id.id for payline in paylines]
            domain += [('id', 'not in', move_lines_ids)]


        paylines = self.env['account.document.line'].search([
            ('state', 'in', ('draft', 'open', 'advanced')),
            ('move_line_id', '!=', False)])
        domain += [('order_id', '=', False)]
        if paylines:
            if self.order_id.payment_type == 'inbound':
                move_lines_ids = [payline.move_line_id.id for payline in
                                  paylines.filtered(lambda r: r.move_line_id.account_internal_type == 'receivable') if
                                  payline.move_line_id.amount_pending_on_receivables <= 0]
                move_lines_ids += [payline.move_line_id.id for payline in
                                   paylines.filtered(lambda r: r.move_line_id.account_internal_type != 'receivable')]
            else:
                move_lines_ids = [payline.move_line_id.id for payline in paylines]
            domain += [('id', 'not in', move_lines_ids)]

        return domain
