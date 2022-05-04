from odoo import fields, models, api


class ModelName(models.Model):
    _inherit = 'account.payment.mode'

    cancellation_account_id = fields.Many2one(
        'account.account', string="Cancellation account"
    )
    cancellation_journal_id = fields.Many2one(
        'account.journal', string="Cancellation journal"
    )

    take_sale_department_account = fields.Boolean(
        string="Coger cuenta departamento facturación"
    )