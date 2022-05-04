from odoo import models, api
from odoo.tools.misc import formatLang


class AccountPaymentDocumentReport(models.AbstractModel):
    _name = "report.account_payment_document.print_account_payment_document"
    _description = "Technical model for printing payment document"

    @api.model
    def _get_report_values(self, docids, data=None):
        AccountPaymentDocumentObj = self.env["account.payment.document"]
        docs = AccountPaymentDocumentObj.browse(docids)

        return {
            "doc_ids": docids,
            "doc_model": "account.payment.document",
            "docs": docs,
            "data": data,
            "env": self.env,
            "formatLang": formatLang,
        }
