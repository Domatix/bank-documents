from odoo import models, fields, api, _, exceptions
from datetime import timedelta


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    payment_document_ids = fields.One2many(
        comodel_name='account.payment.document',
        inverse_name='payment_order_id',
        string='Received documents',
        readonly=True, states={'draft': [('readonly', False)]})

    partner_ids = fields.Many2many(
        'res.partner',
        string='Partners',
        compute='_compute_partner_ids',
        store=True
    )

    only_docs = fields.Boolean(
        string='Only Payment Documents',
        store=True,
        compute="_computed_only_docs")

    only_move_lines = fields.Boolean(
        string='Only Account Move Lines',
        store=True,
        compute="_computed_move_lines")

    expiration_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Expiration Account Move')

    def button_pay_action(self):

        today = fields.Date.today()
        for order in self:
            if order.date_prefered == 'fixed' and \
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
                    if pline.ml_maturity_date and pline.ml_maturity_date <= today:
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
                                    for move in order.move_ids.filtered(
                                            lambda r: pline.bank_line_id.id in r.line_ids.mapped(
                                                    'bank_payment_line_id').ids):
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
                                    for move in order.move_ids.filtered(
                                            lambda r: pline.bank_line_id.id in r.line_ids.mapped(
                                                    'bank_payment_line_id').ids):
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
                    if all([pline.ml_maturity_date and pline.move_line_id and pline.ml_maturity_date <= today
                            and not pline.move_line_id.reconciled
                            for pline in bline.payment_line_ids]):
                        bline.reconcile_payment_lines()

                if all(order.move_ids.mapped('line_ids').filtered(lambda r: r.credit).mapped('reconciled')):
                    if order.payment_document_ids:
                        if all(order.payment_document_ids.mapped('move_ids').mapped('line_ids').mapped('reconciled')):
                            order.action_done()
                    else:
                        order.action_done()


    @api.depends('payment_line_ids')
    def _compute_partner_ids(self):
        for record in self:
            record.partner_ids = [
                (6, 0, record.payment_line_ids.mapped('partner_id').ids)]

    @api.depends('payment_line_ids', 'payment_document_ids')
    def _computed_only_docs(self):
        for record in self:
            if record.payment_document_ids:
                record.only_docs = True
            else:
                record.only_docs = False

    @api.depends('payment_line_ids', 'payment_document_ids')
    def _computed_move_lines(self):
        for record in self:
            if record.payment_line_ids and not record.payment_document_ids:
                record.only_move_lines = True
            else:
                record.only_move_lines = False

    def draft2open(self):
        for doc in self.payment_document_ids:
            if doc.payment_mode_id.offsetting_account == 'bank_account':
                account_id = doc.journal_id.default_debit_account_id.id
            elif doc.payment_mode_id.offsetting_account == 'transfer_account':
                account_id = doc.payment_mode_id.transfer_account_id.id
            if account_id:
                move_list = doc.mapped(
                    'move_ids').mapped('line_ids').filtered(
                        lambda r: r.account_id.id == account_id)
                move_list -= self.payment_line_ids.mapped('move_line_id')
                move_list.create_payment_line_from_move_line(
                    doc.payment_order_id)
        return super(AccountPaymentOrder, self).draft2open()

    def _create_reconcile_move(self, hashcode, blines):
        self.ensure_one()
        post_move = self.payment_mode_id.post_move
        am_obj = self.env['account.move']
        mvals = self._prepare_move(blines)
        move = am_obj.create(mvals)
        if self.date_prefered == 'now':
            blines.reconcile_payment_lines()

            ### PAGO INMEDIATO DEL PAGARE ###

            for doc in self.payment_line_ids.mapped('move_line_id').mapped('move_id').mapped(
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


        elif self.date_prefered == 'due' or self.date_prefered == 'fixed':
            for line in self.payment_line_ids:
                if not line.move_line_id.amount_pending_on_receivables:
                    line.move_line_id.not_reconcile = True

        if post_move:
            move.post()

    def generated2uploaded(self):
        super(AccountPaymentOrder, self).generated2uploaded()
        for order in self:
            if order.only_docs:
                for line in order.payment_line_ids.filtered(lambda r: not r.move_line_id.reconciled and not r.move_line_id.move_id.is_invoice()):
                    lines_to_rec = line.move_line_id
                    lines_to_rec |= order.move_ids.mapped('line_ids').filtered(
                        lambda r: lines_to_rec.id in r.bank_payment_line_id.mapped(
                            'payment_line_ids').mapped('move_line_id').ids)
                    lines_to_rec.reconcile()
        return True

    def _prepare_move_line_partner_account(self, bank_line):
        vals = super(AccountPaymentOrder, self)._prepare_move_line_partner_account(bank_line)
        vals['not_reconcile'] = True
        vals['date_maturity'] = bank_line.date
        return vals

    def _prepare_move_line_offsetting_account(
            self, amount_company_currency, amount_payment_currency,
            bank_lines):
        vals = super(AccountPaymentOrder, self)._prepare_move_line_offsetting_account(amount_company_currency, amount_payment_currency,
            bank_lines)
        vals['order_id'] = self.id
        return vals

    def action_cancel(self):
        res = super().action_cancel()
        for order in self:
            docs = order.payment_line_ids.mapped('move_line_id').mapped('move_id').mapped(
                'line_ids').mapped('document_line_id').mapped('document_id')
            for doc in docs:
                for line in doc.move_ids.mapped('line_ids'):
                    line.remove_move_reconcile()
                doc.write({
                    'state': 'open'
                })
        self.payment_line_ids.move_line_id._compute_amount_on_receivables()
        for line in self.payment_line_ids.move_line_id:
            if line.amount_pending_on_receivables:
                line.not_reconcile = False

    def write(self, values):
        if self.payment_type == 'inbound' and 'payment_line_ids' in values:
            for line in values['payment_line_ids']:
                if line[0] == 0:
                    #Si la linea tiene apunte contable controlamos la cantidad que se introduce
                    #Si la linea no tiene apunte podemos meter cualquier cantidad
                    if 'move_line_id' in line[2] and 'amount_currency' in line[2] and line[2]['move_line_id']:
                        move_line_id = self.env['account.move.line'].search([('id', '=', line[2]['move_line_id'])])
                        new_amount = line[2]['amount_currency']
                        if move_line_id.move_id.type == 'out_invoice' and new_amount > \
                                move_line_id.amount_pending_on_receivables:
                            raise exceptions.Warning(
                                "El importe establecido de la linea {} supera la cantidad pendiente sin "
                                "documento.".format(
                                    line[2]['communication'] if 'communication' in line[
                                        2] else "False"))
                        if new_amount > move_line_id.amount_residual:
                            raise exceptions.Warning(
                                "El importe establecido de la linea {} supera el importe residual.".format(
                                    line[2]['communication'] if 'communication' in line[
                                        2] else False))
                elif line[0] == 1:
                    payment_line = self.env['account.payment.line'].browse(line[1])
                    move_line_id = False
                    if 'amount_currency' in line[2] and 'move_line_id' not in line[2]:
                        #Puede haber apunte contable o no
                        move_line_id = payment_line.move_line_id
                    elif 'amount_currency' in line[2] and 'move_line_id' in line[2] and line[2]['move_line_id']:
                        move_line_id = self.env['account.move.line'].browse(line[2]['move_line_id'])

                    if move_line_id:
                        actual_amount = payment_line.amount_currency
                        new_amount = line[2]['amount_currency']
                        if move_line_id.move_id.type == 'out_invoice' and new_amount - \
                                actual_amount \
                                > move_line_id.amount_pending_on_receivables:
                            raise exceptions.Warning(
                                "El importe establecido de la linea {} supera la cantidad pendiente sin "
                                "documento.".format(
                                    payment_line.communication))
                        elif move_line_id.document:
                            if move_line_id.amount_residual != new_amount:
                                raise exceptions.Warning(
                                    "Si no se introduce el importe completo del documento {} no podrá remesarse la cantidad pendiente.".format(
                                        move_line_id.name
                                    )
                                )
                        if new_amount > move_line_id.amount_residual:
                            raise exceptions.Warning(
                                "El importe establecido de la linea {} supera el importe residual.".format(
                                    payment_line.communication))

        if 'payment_line_ids' in values:
            for line in values['payment_line_ids']:
                if line[0] == 2:
                    document_id = self.env['account.payment.line'].search([('id', '=', line[1])]).move_line_id.move_id.payment_document_id
                    if document_id:
                        self.payment_document_ids = [
                            (3, document_id.id)]
                        document_id.payment_order_id = False

        return super(AccountPaymentOrder, self).write(values)