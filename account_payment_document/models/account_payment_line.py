# © 2015-2016 Akretion - Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPaymentLine(models.Model):
    _inherit = "account.payment.line"

    def create(self, vals):
        res = super(AccountPaymentLine, self).create(vals)
        for line in res:
            if line.move_line_id and line.move_line_id.move_id.is_invoice():
                line.move_line_id.move_id.message_post(
                    body="Factura introducida en orden de cobro {}. Cantidad: {}".format(line.order_id.name, line.amount_currency)
                )
        return res

    def unlink(self):
        for line in self:
            if line.move_line_id and line.move_line_id.move_id.is_invoice():
                line.move_line_id.move_id.message_post(
                    body="Factura extraída de la orden de cobro {}.".format(line.order_id.name)
                )
        return super(AccountPaymentLine, self).unlink()



    def write(self, values):
        for record in self:
            if 'amount_currency' in values and record.move_line_id and record.move_line_id.move_id.is_invoice():
                record.move_line_id.move_id.message_post(
                    body="Actualizada cantidad en orden de cobro {}. {} {} {}".format(record.order_id.name, record.amount_currency, u'\N{Rightwards Arrow with Equilateral Arrowhead}', values['amount_currency'])
                )
        return super(AccountPaymentLine, self).write(values)