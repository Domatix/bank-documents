from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, Warning as UserError
from odoo.tools import float_compare


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def remove_move_reconcile(self):
        # Payment partial reconcile

        rec_partial_reconcile = self.mapped('matched_debit_ids') + self.mapped('matched_credit_ids')
        cancel_return = False
        if any([move.is_invoice() for move in rec_partial_reconcile['origin_returned_move_ids'].mapped('move_id')]):
            cancel_return = True
        debit_move_id = rec_partial_reconcile['debit_move_id']
        if debit_move_id and not cancel_return:
            debit_move_id.write({
                'not_reconcile': False
            })
        elif debit_move_id and cancel_return:
            rec_partial_reconcile['origin_returned_move_ids'].write({
                'not_reconcile': True
            })
        super().remove_move_reconcile()