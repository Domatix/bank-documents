from odoo import fields, models, api
from odoo.osv import expression


class AccountReconciliation(models.AbstractModel):
    _inherit = 'account.reconciliation.widget'

    @api.model
    def _domain_move_lines_for_reconciliation(self, st_line, aml_accounts, partner_id, excluded_ids=None, search_str=False, mode='rp'):
        domain = super(AccountReconciliation, self)._domain_move_lines_for_reconciliation(
            st_line, aml_accounts, partner_id, excluded_ids=excluded_ids, search_str=search_str, mode=mode)
        domain = expression.AND([domain, [('not_reconcile', '=', False)]])
        return domain