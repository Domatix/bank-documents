from odoo import api, fields, models, _


class AccountPaymentDocumentRecoveryLine(models.Model):
    _name = "account.payment.document.recovery.line"

    document_id = fields.Many2one(
        comodel_name='account.payment.document',
        string='Documento recibido',
        required=True)

    recovery_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento de recuperación',
        required=True)

    order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Órden de cobro',
        required=True)