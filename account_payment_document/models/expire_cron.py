from odoo import models, fields, _
# from datetime import timedelta


class ExpireOrderCron(models.Model):
    _name = "expire.order.cron"
    _description = "Cron to reconcile payments on expiration orders"

    def revision_over_due_orders(self):

        docs = self.env['account.payment.document'].search([])
        # CON ESTO ESTABLECEMOS LA RELACIÓN BIEN HECHA ENTRE ORDENES Y DOCUMENTOS
        for doc in docs:
            for line in doc.move_ids.mapped('line_ids').filtered(lambda r: r.debit):
                if line.payment_line_ids:
                    if doc not in line.payment_line_ids[0].order_id.payment_document_ids:
                        line.payment_line_ids[0].order_id.payment_document_ids = [(4, doc.id)]

        # all_orders = self.env['account.payment.order'].search([
        #     ('state', '=', 'uploaded')
        # ])
        # for order in all_orders:
        #     for line in order.payment_line_ids:
        #         line.move_line_id.not_reconcile = True
        #     for move in order.move_ids:
        #         for line in move.line_ids:
        #             if line.credit > 0:
        #                 line.not_reconcile = True
        # return True

        # today = fields.Date.today() + timedelta(days=365)
        today = fields.Date.today()
        overdue_payment_orders = self.env['account.payment.order'].search([
            ('date_prefered', '!=', 'now'),
            ('state', 'in', ['uploaded', 'done']),
        ])


        for order in overdue_payment_orders:
            if order.date_prefered == 'fixed' and\
             order.date_scheduled <= today:
                amlo = self.env["account.move.line"]
                transit_mlines = amlo.search([("bank_payment_line_id", "in", order.bank_line_ids.ids)])
                transit_mlines = transit_mlines.filtered(lambda r: r.reconciled)
                order.bank_line_ids.filtered(
                    lambda r: r.id not in transit_mlines.mapped('bank_payment_line_id').ids).filtered(
                    lambda j: not all(j.payment_line_ids.move_line_id.mapped('reconciled'))).reconcile_payment_lines()

                ### PAGO INMEDIATO DEL PAGARE ###

                for doc in order.payment_line_ids.mapped('move_line_id').mapped('move_id').mapped(
                        'line_ids').mapped('document_line_id').mapped('document_id'):
                    # Payment of the invoice or the origin move lines
                    for line in doc.document_line_ids:
                        lines_to_rec = line.move_line_id
                        transit_mlines = doc.move_ids.mapped('line_ids').filtered(
                            lambda r: r.document_line_id.id == line.id)
                        assert len(transit_mlines) == 1, \
                            'We should have only 1 move'
                        lines_to_rec |= transit_mlines
                        lines_to_rec.filtered(lambda r: not r.reconciled).reconcile()

                    # Esto no contempla los pagos parciales
                    if False not in doc.move_ids.line_ids.mapped('reconciled'):
                        doc.action_paid()

                ### ### ### ### ### ### ### ###
                order.action_done()
            # For those orders with date prefered = due
            elif order.date_prefered == 'due':
                count = 0


                # Iterate payment lines to reconcile expired ones
                for pline in order.payment_line_ids:
                    if pline.ml_maturity_date <= today:
                        doc = pline.move_line_id.move_id.line_ids.mapped('document_line_id')
                        # If line is related to a payment document AND the payment mode of this document has
                        # charge_financed = True, we create the cancellation move.
                        if doc:
                            doc = doc[0].document_id
                            if doc.payment_mode_id.charge_financed:
                                if doc.payment_type == 'outbound':
                                    name = _('Expired Payment document %s') % doc.name
                                else:
                                    name = _('Expired Debit document %s') % doc.name

                                vals = {
                                    'journal_id': order.payment_mode_id.cancellation_journal_id.id,
                                    'ref': name,
                                    'line_ids': [],
                                }
                                debit_account_id = order.payment_mode_id.cancellation_account_id.id
                                credit_account_id = False
                                if order.payment_mode_id.offsetting_account == \
                                        'bank_account':
                                    credit_account_id = order.journal_id. \
                                        default_debit_account_id.id
                                elif order.payment_mode_id.offsetting_account == \
                                        'transfer_account':
                                    credit_account_id = order.payment_mode_id. \
                                        transfer_account_id.id
                                if debit_account_id and credit_account_id:
                                    for move in order.move_ids.filtered(lambda r: pline.bank_line_id.id in r.line_ids.mapped('bank_payment_line_id').ids):
                                        reconciled_account = move.line_ids.mapped(
                                            'account_id').filtered(
                                            lambda r: r.id == credit_account_id)
                                        reconciled_line = move.line_ids.filtered(
                                            lambda r: r.account_id.id == reconciled_account.id)
                                        currency_id = False
                                        amount_currency = False
                                        if reconciled_line:
                                            currency_id = reconciled_line[0].currency_id
                                            amount_currency = reconciled_line[0].amount_currency

                                        total_debit = sum(line.debit for line in move.line_ids)
                                        total_credit = sum(line.credit for line in move.line_ids)
                                        debit_line = {
                                            'name': name,
                                            'partner_id': doc.partner_id.id,
                                            'account_id': debit_account_id,
                                            'credit': 0,
                                            'debit': total_debit,
                                            'currency_id': currency_id.id if currency_id
                                            else False,
                                            'amount_currency': amount_currency.id
                                            if amount_currency else False,

                                        }
                                        credit_line = {
                                            'name': name,
                                            'partner_id': doc.partner_id.id,
                                            'account_id': credit_account_id,
                                            'credit': total_credit,
                                            'debit': 0,
                                            'currency_id': currency_id.id if currency_id
                                            else False,
                                            'amount_currency': amount_currency.id
                                            if amount_currency else False,

                                        }
                                    vals['line_ids'].append((0, 0, debit_line))
                                    vals['line_ids'].append((0, 0, credit_line))
                                    # Cancellation move creation
                                    move = self.env['account.move'].create(vals)
                                    # Change state of document to 'paid'
                                    doc.write({
                                        'state': 'paid',
                                    })
                                    doc.expiration_move_id = move.id
                                    if doc.payment_mode_id.post_move:
                                        move.post()

                                        # Reconciliation of lines
                                        lines_to_rec = doc.expiration_move_id.line_ids.filtered(lambda r: r.credit > 0)
                                        lines_to_rec |= order.move_ids.line_ids.filtered(lambda r: r.debit > 0)
                                        lines_to_rec.filtered(lambda r: not r.reconciled).reconcile()

                            # Payment of the invoice or the origin move lines
                            for line in doc.document_line_ids:
                                lines_to_rec = line.move_line_id
                                transit_mlines = doc.move_ids.mapped('line_ids').filtered(
                                    lambda r: r.document_line_id.id == line.id)
                                assert len(transit_mlines) == 1, \
                                    'We should have only 1 move'
                                lines_to_rec |= transit_mlines
                                lines_to_rec.filtered(lambda r: not r.reconciled).reconcile()

                            if False not in doc.move_ids.line_ids.mapped('reconciled'):
                                doc.action_paid()

                        else:
                            # If there is no document related to the line of the order AND the order's payment mode has
                            # charge_financed = True then we create the cancellation move
                            doc = order
                            if order.payment_mode_id.charge_financed == True:
                                if order.payment_type == 'outbound':
                                    name = _('Expired Payment order %s') % order.name
                                else:
                                    name = _('Expired Debit order %s') % order.name

                                vals = {
                                    'journal_id': order.payment_mode_id.cancellation_journal_id.id,
                                    'ref': name,
                                    'line_ids': [],
                                }
                                debit_account_id = order.payment_mode_id.cancellation_account_id.id
                                credit_account_id = False
                                if order.payment_mode_id.offsetting_account == \
                                        'bank_account':
                                    credit_account_id = order.journal_id. \
                                        default_debit_account_id.id
                                elif order.payment_mode_id.offsetting_account == \
                                        'transfer_account':
                                    credit_account_id = order.payment_mode_id. \
                                        transfer_account_id.id
                                if debit_account_id and credit_account_id:
                                    for move in order.move_ids.filtered(lambda r: pline.bank_line_id.id in r.line_ids.mapped('bank_payment_line_id').ids):
                                        reconciled_account = move.line_ids.mapped(
                                            'account_id').filtered(
                                            lambda r: r.id == credit_account_id)
                                        reconciled_line = move.line_ids.filtered(
                                            lambda r: r.account_id.id == reconciled_account.id)
                                        currency_id = False
                                        amount_currency = False
                                        if reconciled_line:
                                            currency_id = reconciled_line[0].currency_id
                                            amount_currency = reconciled_line[0].amount_currency

                                        total_debit = sum(line.debit for line in move.line_ids)
                                        total_credit = sum(line.credit for line in move.line_ids)
                                        debit_line = {
                                            'name': name,
                                            'partner_id': move.partner_id.id,
                                            'account_id': debit_account_id,
                                            'credit': 0,
                                            'debit': total_debit,
                                            'currency_id': currency_id.id if currency_id
                                            else False,
                                            'amount_currency': amount_currency.id
                                            if amount_currency else False,

                                        }
                                        credit_line = {
                                            'name': name,
                                            'partner_id': move.partner_id.id,
                                            'account_id': credit_account_id,
                                            'credit': total_credit,
                                            'debit': 0,
                                            'currency_id': currency_id.id if currency_id
                                            else False,
                                            'amount_currency': amount_currency.id
                                            if amount_currency else False,

                                        }
                                    vals['line_ids'].append((0, 0, debit_line))
                                    vals['line_ids'].append((0, 0, credit_line))
                                    move = self.env['account.move'].create(vals)

                                    order.expiration_move_id = move.id
                                    if order.payment_mode_id.post_move:
                                        move.post()

                                        lines_to_rec = order.expiration_move_id.line_ids.filtered(lambda r: r.credit > 0)
                                        lines_to_rec |= order.move_ids.line_ids.filtered(lambda r: r.debit > 0)
                                        lines_to_rec.filtered(lambda r: not r.reconciled).reconcile()

                            # for line in doc.payment_line_ids:
                            #     lines_to_rec = line.move_line_id
                            #     transit_mlines = doc.move_ids.mapped('line_ids').filtered(
                            #         lambda r: r.document_line_id.id == line.id)
                            #     assert len(transit_mlines) == 1, \
                            #         'We should have only 1 move'
                            #     lines_to_rec |= transit_mlines
                            #     lines_to_rec.reconcile()

                for bline in order.bank_line_ids:
                    if all([pline.ml_maturity_date <= today
                            and not pline.move_line_id.reconciled
                            for pline in bline.payment_line_ids]):
                        bline.reconcile_payment_lines()

                if all(order.move_ids.mapped('line_ids').filtered(lambda r: r.credit).mapped('reconciled')):
                    if order.payment_document_ids:
                        if all(order.payment_document_ids.mapped('move_ids').mapped('line_ids').mapped('reconciled')):
                            order.action_done()
                    else:
                        order.action_done()