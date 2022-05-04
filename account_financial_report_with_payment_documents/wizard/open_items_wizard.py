from odoo import api, fields, models


class OpenItemsReportWizard(models.TransientModel):
    """Open items report wizard."""

    _inherit = "open.items.report.wizard"

    invoice_date_due_at = fields.Date(string="(Hasta) Fecha de vencimiento")

    def _prepare_report_open_items(self):
        res = super(OpenItemsReportWizard, self)._prepare_report_open_items()
        res['invoice_date_due_at'] = self.invoice_date_due_at or False
        return res
