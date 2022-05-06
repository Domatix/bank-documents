from odoo import models, fields, api, _, exceptions
from odoo.exceptions import UserError, ValidationError


class AccountPaymentDocument(models.Model):
    _name = 'account.payment.document'
    _description = 'Payment Document'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(
        string='Name', readonly=False, required=True)

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        readonly=True,
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
        required=True,
        index=True,
        track_visibility='always',
    )

    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        copy=False,
        string='Related payment order')

    payment_mode_id = fields.Many2one(
        'account.payment.mode', 'Payment Mode', required=True,
        ondelete='restrict', track_visibility='onchange',
        readonly=True, states={'draft': [('readonly', False)]})

    payment_method_id = fields.Many2one(
        'account.payment.method', related='payment_mode_id.payment_method_id',
        readonly=True, store=True)

    payment_type = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
        ], string='Payment Type', readonly=True, required=True)

    company_id = fields.Many2one(
        related='payment_mode_id.company_id', store=True, readonly=True)

    company_currency_id = fields.Many2one(
        related='payment_mode_id.company_id.currency_id', store=True,
        readonly=True)

    bank_account_link = fields.Selection(
        related='payment_mode_id.bank_account_link', readonly=True)

    allowed_journal_ids = fields.Many2many(
        comodel_name='account.journal',
        compute="_compute_allowed_journal_ids",
        string="Allowed journals",
    )

    journal_id = fields.Many2one(
        'account.journal', string='Journal', ondelete='restrict',
        readonly=True, states={'draft': [('readonly', False)]},
        track_visibility='onchange')

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('open', 'Confirmed'),
            ('advanced', 'Advanced'),
            ('paid', 'Paid'),
            ('unpaid', 'Unpaid'),
            ('cancel', 'Cancel'),
        ], string='Status', readonly=True, copy=False, default='draft',
        track_visibility='onchange')

    date_prefered = fields.Selection([
        ('now', 'Immediately'),
        ('due', 'Due Date'),
        ], string='Payment Due Date Type', required=True, default='due',
        track_visibility='onchange', readonly=True,
        states={'draft': [('readonly', False)]})

    date_due = fields.Date(
        string='Payment Due Date', readonly=True,
        states={'draft': [('readonly', False)]}, track_visibility='onchange',
        help="Select a date if you selected 'Due Date' "
        "as the Payment Due Date Type.")

    date_paid = fields.Date(string='Paid Date', readonly=True)

    date = fields.Date(string='Date')

    document_line_ids = fields.One2many(
        'account.document.line', 'document_id', string='Transaction Lines',
        readonly=True, states={'draft': [('readonly', False)]})

    total_company_currency = fields.Monetary(
        compute='_compute_total', store=True, readonly=True,
        currency_field='company_currency_id')

    move_ids = fields.One2many(
        'account.move', 'payment_document_id', string='Journal Entries',
        readonly=True)

    description = fields.Char()

    returned = fields.Boolean(
        string='Recuperado',
    )

    # document_due_move_account_id = fields.Many2one(
    #     'account.account',
    #     'Debit default account for account moves for expiration',
    #     readonly=True,
    #     states={'draft': [('readonly', False)]}
    # )
    #
    # expiration_move_journal_id = fields.Many2one(
    #     'account.journal', string='Expiration Move Journal',
    #     ondelete='restrict', readonly=True,
    #     states={'draft': [('readonly', False)]},
    #     track_visibility='onchange')

    expiration_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Expiration Account Move')

    recovery_line_ids = fields.One2many(
        comodel_name='account.payment.document.recovery.line',
        inverse_name='document_id',
        string='Histórico recuperaciones',
        required=False)

    def copy(self, default=None):
        default = dict(default or {})
        if "name" not in default or\
                ("name" in default and not default["name"]):
            default["name"] = self.name + " (copia)"
        return super(AccountPaymentDocument, self).copy(default)

    @api.depends('payment_mode_id')
    def _compute_allowed_journal_ids(self):
        for record in self:
            if record.payment_mode_id.bank_account_link == 'fixed':
                record.allowed_journal_ids = (
                    record.payment_mode_id.fixed_journal_id)
            elif record.payment_mode_id.bank_account_link == 'variable':
                record.allowed_journal_ids = (
                    record.payment_mode_id.variable_journal_ids)
            else:
                record.allowed_journal_ids = False

    @api.depends(
        'document_line_ids', 'document_line_ids.amount_company_currency')
    def _compute_total(self):
        for rec in self:
            rec.total_company_currency = sum(
                rec.mapped('document_line_ids.amount_company_currency') or
                [0.0])

    def unlink(self):
        for document in self:
            if document.state != 'draft':
                raise UserError(_(
                    "You cannot delete a non draft payment document. You can "
                    "cancel it in order to do so."))
        return super(AccountPaymentDocument, self).unlink()

    @api.constrains('payment_type', 'payment_mode_id')
    def payment_document_constraints(self):
        for document in self:
            if (
                    document.payment_mode_id.payment_type and
                    document.payment_mode_id.payment_type !=
                    document.payment_type):
                raise ValidationError(_(
                    "The payment type (%s) is not the same as the payment "
                    "type of the payment mode (%s)") % (
                        document.payment_type,
                        document.payment_mode_id.payment_type))


    #@api.constrains('date_due')
    #def check_date_due(self):
    #    today = fields.Date.context_today(self)
    #    for document in self:
    #        if document.date_due:
    #            if document.date_due < today:
    #                raise ValidationError(_(
    #                    "On payment document %s, the Payment Due Date "
    #                    "is in the past (%s).")
    #                    % (document.name, document.date_due))

    @api.model
    def create(self, vals):
        if not vals.get('date'):
            vals['date'] = fields.Date.context_today(self)
        if vals.get('payment_mode_id'):
            payment_mode = self.env['account.payment.mode'].browse(
                vals['payment_mode_id'])
            vals['payment_type'] = payment_mode.payment_type
            if payment_mode.bank_account_link == 'fixed':
                vals['journal_id'] = payment_mode.fixed_journal_id.id
            if (
                    not vals.get('date_prefered') and
                    payment_mode.default_date_prefered and
                    payment_mode.default_date_prefered != 'fixed'):
                vals['date_prefered'] = payment_mode.default_date_prefered
            else:
                vals['date_prefered'] = 'due'
        return super(AccountPaymentDocument, self).create(vals)

    @api.onchange('payment_mode_id')
    def payment_mode_id_change(self):
        if len(self.allowed_journal_ids) == 1:
            self.journal_id = self.allowed_journal_ids
        if (
                self.payment_mode_id.default_date_prefered and
                self.payment_mode_id.default_date_prefered != 'fixed'):
            self.date_prefered = self.payment_mode_id.default_date_prefered
        else:
            self.date_prefered = 'due'

    def action_paid(self):
        self.write({
            'date_paid': fields.Date.context_today(self),
            'state': 'paid',
            })
        return True

    def _prepare_unpaid_move_vals(self):
        self.ensure_one()
        return {
            "name": "/",
            "ref": _("Recuperación %s") % self.name,
            "journal_id": self.journal_id.id,
            "date": self.date,
            "company_id": self.company_id.id,
        }

    def action_unpaid(self):
        self.ensure_one()
        if self.payment_type != "inbound":
            raise UserError(
                _("Solo se pueden recuperar documentos recibidos.")
            )
        if self.state not in ['open', 'advanced', 'paid']:
            return True

        move_line_model = self.env["account.move.line"]
        unpaid_move = self.env["account.move"].create(self._prepare_unpaid_move_vals())
        for move in self.move_ids:
            debit_line = move.line_ids.filtered(lambda r: r.debit)
            document_id = debit_line.move_id.payment_document_id
            order_id = document_id.payment_order_id
            unpaid_debit_line_vals = {
                "name": _("Recuperación %s") % self.name,
                "debit": move.amount_total_signed,
                "credit": 0.0,
                "account_id": debit_line.account_id.id,
                "partner_id": move.partner_id.id,
                "journal_id": move.journal_id.id,
                "move_id": unpaid_move.id,
            }
            unpaid_debit_move_line = move_line_model.with_context(check_move_validity=False).create(
                unpaid_debit_line_vals
            )

            credit_line = debit_line.matched_credit_ids.mapped("credit_move_id")
            credit_line.remove_move_reconcile()
            (credit_line | unpaid_debit_move_line).with_context(
                check_move_validity=False
            ).reconcile()
            credit_line.mapped("matched_debit_ids").write(
                {"origin_returned_move_ids": [(6, 0, debit_line.ids)]}
            )

            unpaid_credit_move_line = move_line_model.create({
                "name": unpaid_move.ref,
                "debit": 0.0,
                "credit": move.amount_total_signed,
                "account_id": credit_line.move_id.line_ids.filtered(lambda r: r.debit)[0].account_id.id,
                "move_id": unpaid_move.id,
                "journal_id": unpaid_move.journal_id.id,
            })

            # self._auto_reconcile(unpaid_credit_move_line, credit_line, move.amount_total_signed)
            unpaid_move.post()

            (credit_line.move_id.line_ids.filtered(lambda r: r.debit) | unpaid_credit_move_line).reconcile()

            payline = self.env['account.payment.line'].search([
                ('order_id', '=', order_id.id),
                ('move_line_id', '=', debit_line.id)])
            payline.move_line_id = False

            self.env['account.payment.document.recovery.line'].create({
                'document_id': self.id,
                'recovery_move_id': unpaid_move.id,
                'order_id': order_id.id
            })

        self.write({
            'state': 'unpaid',
            'returned': True,
            'payment_order_id': False
            })

        return True

    def action_paid_cancel(self):
        if self.payment_order_id:
            raise UserError(_(
                'You can\'t cancel a received document that is already in a debit order.'))
        for move in self.move_ids:
            move.button_cancel()
            for move_line in move.line_ids:
                move_line.remove_move_reconcile()
            move.with_context(force_delete=True).unlink()
        self.action_cancel()
        for line in self.document_line_ids.move_line_id:
            if line.amount_pending_on_receivables:
                line.not_reconcile = False
        return True

    def action_cancel(self):
        for document in self:
            document.write({'state': 'cancel'})
        return True

    def cancel2draft(self):
        self.write({'state': 'draft'})
        return True

    def open2advanced(self):
        self.write({'state': 'advanced'})
        return True

    def draft2open(self):
        today = fields.Date.context_today(self)
        for document in self:
            if not document.journal_id:
                raise UserError(_(
                    'Missing Journal on payment document %s.') % document.name)
            if (
                    document.payment_method_id.bank_account_required and
                    not document.journal_id.bank_account_id):
                raise UserError(_(
                    "Missing bank account on journal '%s'.")
                    % document.journal_id.display_name)
            if not document.document_line_ids:
                raise UserError(_(
                    'There are no transactions on payment document %s.')
                    % document.name)
            for payline in document.document_line_ids:
                if document.date_prefered == "due":
                    requested_date = document.date_due or today
                elif document.date_prefered == "fixed":
                    requested_date = document.date_scheduled or today
                else:
                    requested_date = today
                # No payment date in the past
                if requested_date < today:
                    requested_date = today
                with self.env.norecompute():
                    payline.date = requested_date

            document.recompute()
            if document.payment_mode_id.generate_move:
                document.generate_move()
        self.write({'state': 'open'})
        return True

    def _create_reconcile_move(self):
        self.ensure_one()
        post_move = self.payment_mode_id.post_move
        am_obj = self.env['account.move']
        mvals = self._prepare_move()
        move = am_obj.create(mvals)
        if post_move:
            move.post()

    def generate_move(self):
        """
        Create the moves that 'pay off' the move lines from
        the payment/debit document.
        """
        self.ensure_one()
        self._create_reconcile_move()

    def _prepare_move(self):
        if self.payment_type == 'outbound':
            ref = _('Payment document %s') % self.name
        else:
            ref = _('Debit document %s') % self.name
        if self.payment_mode_id.offsetting_account == 'bank_account':
            journal_id = self.journal_id.id
        elif self.payment_mode_id.offsetting_account == 'transfer_account':
            journal_id = self.payment_mode_id.transfer_journal_id.id
        vals = {
            'journal_id': journal_id,
            'ref': ref,
            'payment_document_id': self.id,
            'line_ids': [],
            }
        if self.document_line_ids:
            vals.update({"date": self.date or fields.Date.today()})

        total_company_currency = total_payment_currency = 0
        for doc_line in self.document_line_ids:
            if not doc_line.move_line_id.amount_pending_on_receivables:
                doc_line.move_line_id.not_reconcile = True
            total_company_currency += doc_line.amount_company_currency
            total_payment_currency += doc_line.amount_currency
            partner_ml_vals = self._prepare_move_line_partner_account(doc_line)
            vals['line_ids'].append((0, 0, partner_ml_vals))

        trf_ml_vals = self._prepare_move_line_offsetting_account(
            total_company_currency, total_payment_currency)
        vals['line_ids'].append((0, 0, trf_ml_vals))
        return vals

    def _prepare_move_line_partner_account(self, doc_line):
        if doc_line.move_line_id:
            account_id = doc_line.move_line_id.account_id.id
        else:
            if self.payment_type == 'inbound':
                account_id =\
                    doc_line.partner_id.property_account_receivable_id.id
            else:
                account_id =\
                    doc_line.partner_id.property_account_payable_id.id
        if self.payment_type == 'outbound':
            name = _('Payment document line %s') % doc_line.move_line_id.name
        else:
            name = _('Debit document line %s') % doc_line.move_line_id.name
        vals = {
            'name': name,
            'partner_id': doc_line.partner_id.id,
            'document_line_id': doc_line.id,
            'not_reconcile': True if doc_line.move_line_id else False,
            'date_maturity': doc_line.ml_maturity_date or doc_line.date,
            'account_id': account_id,
            'credit': (self.payment_type == 'inbound' and
                       doc_line.amount_company_currency or 0.0),
            'debit': (self.payment_type == 'outbound' and
                      doc_line.amount_company_currency or 0.0),
            }

        if doc_line.currency_id != doc_line.company_currency_id:
            sign = self.payment_type == 'inbound' and -1 or 1
            vals.update({
                'currency_id': doc_line.currency_id.id,
                'amount_currency': doc_line.amount_currency * sign,
                })
        return vals

    def _prepare_move_line_offsetting_account(
            self, amount_company_currency, amount_payment_currency):
        vals = {}
        if self.payment_type == 'outbound':
            name = _('Payment document %s') % self.name
        else:
            name = _('Debit document %s') % self.name
        if self.payment_mode_id.offsetting_account == 'bank_account':
            vals.update({'date': self.date})
        else:
            if self.date_prefered == 'due':
                vals.update({'date_maturity': self.date_due or self.date})
            else:
                vals.update({'date_maturity': self.date})

        if self.payment_mode_id.offsetting_account == 'bank_account':
            account_id = self.journal_id.default_debit_account_id.id
        elif self.payment_mode_id.offsetting_account == 'transfer_account':
            account_id = self.payment_mode_id.transfer_account_id.id
        partner_id = self.partner_id.id
        vals.update({
            'name': name,
            'document': True,
            'partner_id': partner_id,
            'not_reconcile': True,
            'account_id': account_id,
            'credit': (self.payment_type == 'outbound' and
                       amount_company_currency or 0.0),
            'debit': (self.payment_type == 'inbound' and
                      amount_company_currency or 0.0),
        })
        if (
                self.document_line_ids[0].currency_id !=
                self.document_line_ids[0].company_currency_id):
            sign = self.payment_type == 'outbound' and -1 or 1
            vals.update({
                'currency_id': self.document_line_ids[0].currency_id.id,
                'amount_currency': amount_payment_currency * sign,
                })
        return vals


    def write(self, values):
        for record in self:
            if record.payment_type == 'inbound' and 'document_line_ids' in values:
                for line in values['document_line_ids']:
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
                        if 'amount_currency' in line[2]:
                            #Puede haber apunte contable o no
                            payment_line = self.env['account.document.line'].browse(line[1])
                            if payment_line.move_line_id:
                                actual_amount = payment_line.amount_currency
                                new_amount = line[2]['amount_currency']
                                if payment_line.move_line_id.move_id.type == 'out_invoice' and new_amount - \
                                        actual_amount \
                                        > payment_line.move_line_id.amount_pending_on_receivables:
                                    raise exceptions.Warning(
                                        "El importe establecido de la linea {} supera la cantidad pendiente sin "
                                        "documento.".format(
                                            payment_line.communication))
                                if new_amount > payment_line.move_line_id.amount_residual:
                                    raise exceptions.Warning(
                                        "El importe establecido de la linea {} supera el importe residual.".format(
                                            payment_line.communication))

                        if 'move_line_id' in line[2] and line[2]['move_line_id']:
                            if 'amount_currency' in line[2]:
                                payment_line = self.env['account.document.line'].browse(line[1])
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
                                    if new_amount > move_line_id.amount_residual:
                                        raise exceptions.Warning(
                                            "El importe establecido de la linea {} supera el importe residual.".format(
                                                payment_line.communication))
                #1 Creación manual de una linea (todavía no existe)
                # [0, 'virtual_102',
                #  {'currency_id': 1, 'communication_type': 'normal', 'document_id': False, 'move_line_id': 167973,
                #  'date': False, 'amount_currency': 1188.32, 'partner_id': 42472, 'communication': 'FCVG210900190'}]


                #2 Creación manual de una linea (todavía no existe) modificando cantidad
                # [0, 'virtual_102',
                #  {'currency_id': 1, 'communication_type': 'normal', 'document_id': False, 'move_line_id': 167973,
                #   'date': False, 'amount_currency': 100, 'partner_id': 42472, 'communication': 'FCVG210900190'}]


                #3 Creación manual de una linea sin apunte
                # [0, 'virtual_74',
                #  {'currency_id': 1, 'communication_type': 'normal', 'document_id': False, 'move_line_id': False,
                #   'date': False, 'amount_currency': 1188.32, 'partner_id': 42472, 'communication': 'FCVG210900190'}]


                #4 Creación manual de una linea sin apunte modificando cantidad
                # [0, 'virtual_74',
                #  {'currency_id': 1, 'communication_type': 'normal', 'document_id': False, 'move_line_id': False,
                #   'date': False, 'amount_currency': 100, 'partner_id': 42472, 'communication': 'FCVG210900190'}]


                #5 Modificación de una linea (eliminamos apunte)
                # [1, 893, {'move_line_id': False, 'amount_currency': 1188.32, 'partner_id': 42472,
                #           'communication': 'FCVG210900190'}]


                #6 Modificación de una linea (eliminamos apunte y modificamos cantidad)
                # [1, 893,
                #  {'move_line_id': False, 'amount_currency': 100, 'partner_id': 42472, 'communication': 'FCVG210900190'}]


                #7 Modificación de una linea sin apunte (cambiamos cantidad)
                # [1, 893, {'amount_currency': 2000}]


                #8 Modificación de una linea sin apunte (añadimos apunte)
                # [1, 893, {'move_line_id': 167973}]


                #9 Modificación de una linea sin apunte (añadimos apunte y cambiamos cantidad)
                # [1, 893, {'move_line_id': 167973, 'amount_currency': 100}]

                #9 Eliminación de una linea
                # [2, 893, False]
        return super(AccountPaymentDocument, self).write(values)