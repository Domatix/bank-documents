from odoo import api, fields, models, _


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def process_reconciliation(
        self,
        counterpart_aml_dicts=None,
        payment_aml_rec=None,
        new_aml_dicts=None,
            ):
        for aml_dict in new_aml_dicts:
            if 'order_id' in aml_dict:
                order_id = aml_dict.pop('order_id')
                order_id = self.env['account.payment.order'].search(
                    [('id', '=', order_id)])
                for doc in order_id.mapped('payment_document_ids'):
                    if doc.payment_mode_id.charge_financed:
                        doc.open2advanced()
                    self.env['expire.order.cron'].revision_over_due_orders()
                if order_id.payment_mode_id.charge_financed:
                    order_id.mapped('payment_document_ids').open2advanced()
                else:
                    self.env['expire.order.cron'].revision_over_due_orders()
            elif 'document_id' in aml_dict:
                document_id = aml_dict.pop('document_id')
                document_id = self.env['account.payment.document'].search(
                    [('id', '=', document_id)])
                if document_id.payment_mode_id.charge_financed:
                    document_id.open2advanced()
                else:
                    self.env['expire.order.cron'].revision_over_due_orders()
                document_id.open2advanced()
        if counterpart_aml_dicts and counterpart_aml_dicts[0].get('move_line'):
            if counterpart_aml_dicts[0].get('move_line').order_id:
                self.env['expire.order.cron'].revision_over_due_orders()
        moves = super(AccountBankStatementLine, self).process_reconciliation(
            counterpart_aml_dicts, payment_aml_rec, new_aml_dicts)
        return moves
