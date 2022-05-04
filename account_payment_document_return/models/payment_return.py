from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, Warning as UserError
from odoo.tools import float_compare


class PaymentReturn(models.Model):
    _inherit = "payment.return"

    def action_confirm(self):
        self.ensure_one()
        # Check for incomplete lines
        if self.line_ids.filtered(lambda x: not x.move_line_ids):
            raise UserError(
                _("You must input all moves references in the payment return.")
            )
        payment_order_ids = self.env["account.move"]
        move_line_model = self.env["account.move.line"]
        move = self.env["account.move"].create(self._prepare_return_move_vals())
        total_amount = 0.0
        all_move_lines = self.env["account.move.line"]
        for return_line in self.line_ids:
            move_line2_vals = return_line._prepare_return_move_line_vals(move)
            move_line2 = move_line_model.with_context(check_move_validity=False).create(
                move_line2_vals
            )
            total_amount += move_line2.debit
            for move_line in return_line.move_line_ids:
                # move_line: credit on customer account (from payment move)
                # returned_moves: debit on customer account (from invoice move)
                returned_moves = move_line.matched_debit_ids.mapped("debit_move_id")
                all_move_lines |= move_line
                payment_order_ids |= returned_moves.mapped("move_id")
                move_line.remove_move_reconcile()
                (move_line | move_line2).with_context(
                    check_move_validity=False
                ).reconcile()
                return_line.move_line_ids.filtered(lambda r: r.id == move_line.id).mapped("matched_debit_ids").write(
                    {"origin_returned_move_ids": [(6, 0, returned_moves.ids)]}
                )
                for order in payment_order_ids:

                    # Si es una orden de cobro lo que estamos devolviendo tenemos que hacer los asientos inversos de
                    # las facturas (y/o de los documentos recibidos)
                    if order.payment_order_id:
                        order_credit_line = order.line_ids.filtered(lambda r: r.credit > 0)
                        invoice_line = order_credit_line.bank_payment_line_id.mapped(
                            'payment_line_ids')[0].move_line_id

                        invoice_move = self.env['account.move'].create({
                            "name": "/",
                            "ref": _("Return %s") % self.name,
                            "journal_id": order_credit_line.journal_id.id,
                            "date": self.date,
                            "company_id": self.company_id.id,
                        })
                        invoice_return_debit_line_vals = {
                            "name": _("Return %s") % order_credit_line.name,
                            "debit": order_credit_line.credit,
                            "credit": 0.0,
                            "account_id": order_credit_line.account_id.id,
                            "partner_id": order_credit_line.partner_id.id,
                            "journal_id": order_credit_line.journal_id.id,
                            "move_id": invoice_move.id,
                        }
                        invoice_return_debit_line = move_line_model.with_context(
                            check_move_validity=False).create(
                            invoice_return_debit_line_vals
                        )
                        order_credit_line.remove_move_reconcile()
                        (invoice_return_debit_line | order_credit_line).with_context(
                            check_move_validity=False
                        ).reconcile()

                        invoice_return_credit_line_vals = self._prepare_move_line(invoice_move,
                                                                                  invoice_return_debit_line.debit)
                        invoice_return_credit_line = move_line_model.create(invoice_return_credit_line_vals)
                        self._auto_reconcile(invoice_return_credit_line, invoice_return_debit_line,
                                             invoice_return_debit_line.debit)
                        invoice_line.move_id.write(self._prepare_invoice_returned_vals())
                        invoice_move.post()

                        # Si la orden de cobro es de documentos:
                        if invoice_line.move_id.payment_document_id:
                            order_credit_line = invoice_line.move_id.line_ids.filtered(lambda r: r.credit > 0)
                            invoice_line = order_credit_line.document_line_id.move_line_id

                            invoice_move = self.env['account.move'].create({
                                "name": "/",
                                "ref": _("Return %s") % self.name,
                                "journal_id": order_credit_line.journal_id.id,
                                "date": self.date,
                                "company_id": self.company_id.id,
                            })
                            invoice_return_debit_line_vals = {
                                "name": _("Return %s") % order_credit_line.name,
                                "debit": order_credit_line.credit,
                                "credit": 0.0,
                                "account_id": order_credit_line.account_id.id,
                                "partner_id": order_credit_line.partner_id.id,
                                "journal_id": order_credit_line.journal_id.id,
                                "move_id": invoice_move.id,
                            }
                            invoice_return_debit_line = move_line_model.with_context(
                                check_move_validity=False).create(
                                invoice_return_debit_line_vals
                            )
                            order_credit_line.remove_move_reconcile()
                            (invoice_return_debit_line | order_credit_line).with_context(
                                check_move_validity=False
                            ).reconcile()

                            invoice_return_credit_line_vals = self._prepare_move_line(invoice_move,
                                                                                      invoice_return_debit_line.debit)
                            invoice_return_credit_line = move_line_model.create(invoice_return_credit_line_vals)
                            self._auto_reconcile(invoice_return_credit_line, invoice_return_debit_line,
                                                 invoice_return_debit_line.debit)
                            invoice_line.move_id.write(self._prepare_invoice_returned_vals())
                            invoice_move.post()



            if return_line.expense_amount:
                expense_lines_vals = return_line._prepare_expense_lines_vals(move)
                move_line_model.with_context(check_move_validity=False).create(
                    expense_lines_vals
                )
            extra_lines_vals = return_line._prepare_extra_move_lines(move)
            move_line_model.create(extra_lines_vals)
        move_line_vals = self._prepare_move_line(move, total_amount)
        # credit_move_line: credit on transfer or bank account
        credit_move_line = move_line_model.create(move_line_vals)
        # Reconcile (if option enabled)
        self._auto_reconcile(credit_move_line, all_move_lines, total_amount)
        # Write directly because we returned payments just now
        payment_order_ids.write(self._prepare_invoice_returned_vals())
        move.post()
        self.write({"state": "done", "move_id": move.id})
        return True
