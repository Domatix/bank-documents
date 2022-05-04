import operator
from datetime import date, datetime

from odoo import api, models
from odoo.tools import float_is_zero


class OpenItemsReport(models.AbstractModel):
    _inherit = "report.account_financial_report.open_items"

    @api.model
    def _get_move_lines_domain_not_reconciled_custom(
        self, company_id, account_ids, partner_ids, only_posted_moves, date_from, invoice_date_due_at
    ):
        domain = [
            ("account_id", "in", account_ids),
            ("company_id", "=", company_id),
            ("reconciled", "=", False),
        ]
        if partner_ids:
            domain += [("partner_id", "in", partner_ids)]
        if only_posted_moves:
            domain += [("move_id.state", "=", "posted")]
        else:
            domain += [("move_id.state", "in", ["posted", "draft"])]
        if date_from:
            domain += [("date", ">", date_from)]
        # if invoice_date_due_at:
        #     domain += ["|", ("date_maturity", "<", invoice_date_due_at), ("date_maturity", "=", False)]
        return domain


    def _get_data_custom(
        self,
        account_ids,
        partner_ids,
        date_at_object,
        only_posted_moves,
        company_id,
        date_from,
        invoice_date_due_at
    ):
        domain = self._get_move_lines_domain_not_reconciled_custom(
            company_id, account_ids, partner_ids, only_posted_moves, date_from, invoice_date_due_at
        )
        ml_fields = [
            "id",
            "name",
            "date",
            "invoice_date",
            "move_id",
            "journal_id",
            "account_id",
            "partner_id",
            "amount_residual",
            "amount_pending_on_receivables",
            "date_maturity",
            "ref",
            "debit",
            "credit",
            "reconciled",
            "currency_id",
            "amount_currency",
            "amount_residual_currency",
            "payment_mode_id",
            "payment_term_id",
        ]
        move_lines = self.env["account.move.line"].search_read(
            domain=domain, fields=ml_fields
        )

        journals_ids = set()
        partners_ids = set()
        partners_data = {}
        if date_at_object < date.today():
            (
                acc_partial_rec,
                debit_amount,
                credit_amount,
            ) = self._get_account_partial_reconciled(company_id, date_at_object)
            if acc_partial_rec:
                ml_ids = list(map(operator.itemgetter("id"), move_lines))
                debit_ids = list(
                    map(operator.itemgetter("debit_move_id"), acc_partial_rec)
                )
                credit_ids = list(
                    map(operator.itemgetter("credit_move_id"), acc_partial_rec)
                )
                move_lines = self._recalculate_move_lines(
                    move_lines,
                    debit_ids,
                    credit_ids,
                    debit_amount,
                    credit_amount,
                    ml_ids,
                    account_ids,
                    company_id,
                    partner_ids,
                    only_posted_moves,
                )
        move_lines = [
            move_line
            for move_line in move_lines
            if move_line["date"] <= date_at_object
            and not float_is_zero(move_line["amount_residual"], precision_digits=2)
        ]

        open_items_move_lines_data = {}
        for move_line in move_lines:
            journals_ids.add(move_line["journal_id"][0])
            acc_id = move_line["account_id"][0]
            # Partners data
            if move_line["partner_id"]:
                prt_id = move_line["partner_id"][0]
                prt_name = move_line["partner_id"][1]
            else:
                prt_id = 0
                prt_name = "Missing Partner"
            if prt_id not in partners_ids:
                partners_data.update({prt_id: {"id": prt_id, "name": prt_name}})
                partners_ids.add(prt_id)

            # Move line update
            original = 0

            if not float_is_zero(move_line["credit"], precision_digits=2):
                original = move_line["credit"] * (-1)
            if not float_is_zero(move_line["debit"], precision_digits=2):
                original = move_line["debit"]

            if move_line["ref"] == move_line["name"]:
                if move_line["ref"]:
                    ref_label = move_line["ref"]
                else:
                    ref_label = ""
            elif not move_line["ref"]:
                ref_label = move_line["name"]
            elif not move_line["name"]:
                ref_label = move_line["ref"]
            else:
                ref_label = move_line["ref"] + str(" - ") + move_line["name"]

            move_line.update(
                {
                    "date": move_line["date"],
                    "invoice_date": move_line["invoice_date"],
                    "date_maturity": move_line["date_maturity"]
                    and move_line["date_maturity"].strftime("%d/%m/%Y"),
                    "original": original,
                    "partner_id": prt_id,
                    "partner_name": prt_name,
                    "ref_label": ref_label,
                    "journal_id": move_line["journal_id"][0],
                    "move_name": move_line["move_id"][1],
                    "entry_id": move_line["move_id"][0],
                    "currency_id": move_line["currency_id"][0]
                    if move_line["currency_id"]
                    else False,
                    "currency_name": move_line["currency_id"][1]
                    if move_line["currency_id"]
                    else False,
                    "payment_mode_id": move_line["payment_mode_id"][1]
                    if move_line["payment_mode_id"]
                    else False,
                    "payment_term_id": move_line["payment_term_id"][1]
                    if move_line["payment_term_id"]
                    else False,
                }
            )

            # Open Items Move Lines Data
            if acc_id not in open_items_move_lines_data.keys():
                open_items_move_lines_data[acc_id] = {prt_id: [move_line]}
            else:
                if prt_id not in open_items_move_lines_data[acc_id].keys():
                    open_items_move_lines_data[acc_id][prt_id] = [move_line]
                else:
                    open_items_move_lines_data[acc_id][prt_id].append(move_line)
        journals_data = self._get_journals_data(list(journals_ids))
        accounts_data = self._get_accounts_data(open_items_move_lines_data.keys())
        return (
            move_lines,
            partners_data,
            journals_data,
            accounts_data,
            open_items_move_lines_data,
        )

    @api.model
    def _calculate_amounts_custom(self, open_items_move_lines_data, invoice_date_due_at):
        total_amount = {}
        total_amount["total_residual"] = 0
        total_amount["total_original_pre_maturity"] = 0
        total_amount["total_residual_pre_maturity"] = 0
        total_amount["total_original_post_maturity"] = 0
        total_amount["total_residual_post_maturity"] = 0
        total_amount["total_amount_pending_on_receivables"] = 0
        total_amount["total_amount_pending_on_receivables_pre_maturity"] = 0
        total_amount["total_amount_pending_on_receivables_post_maturity"] = 0
        for account_id in open_items_move_lines_data.keys():
            total_amount[account_id] = {}
            total_amount[account_id]["residual"] = 0.0
            total_amount[account_id]["original_pre_maturity"] = 0.0
            total_amount[account_id]["original_post_maturity"] = 0.0
            total_amount[account_id]["residual_pre_maturity"] = 0.0
            total_amount[account_id]["residual_post_maturity"] = 0.0
            total_amount[account_id]["amount_pending_on_receivables"] = 0.0
            total_amount[account_id]["amount_pending_on_receivables_pre_maturity"] = 0.0
            total_amount[account_id]["amount_pending_on_receivables_post_maturity"] = 0.0
            for partner_id in open_items_move_lines_data[account_id].keys():
                total_amount[account_id][partner_id] = {}
                total_amount[account_id][partner_id]["residual"] = 0.0
                total_amount[account_id][partner_id]["original_pre_maturity"] = 0.0
                total_amount[account_id][partner_id]["original_post_maturity"] = 0.0
                total_amount[account_id][partner_id]["residual_pre_maturity"] = 0.0
                total_amount[account_id][partner_id]["residual_post_maturity"] = 0.0
                total_amount[account_id][partner_id]["amount_pending_on_receivables"] = 0.0
                total_amount[account_id][partner_id]["amount_pending_on_receivables_pre_maturity"] = 0.0
                total_amount[account_id][partner_id]["amount_pending_on_receivables_post_maturity"] = 0.0
                for move_line in open_items_move_lines_data[account_id][partner_id]:
                    total_amount[account_id][partner_id]["residual"] += move_line[
                        "amount_residual"
                    ]
                    total_amount[account_id][partner_id]["amount_pending_on_receivables"] += move_line["amount_pending_on_receivables"]
                    total_amount[account_id]["amount_pending_on_receivables"] += move_line["amount_pending_on_receivables"]
                    total_amount[account_id]["residual"] += move_line["amount_residual"]
                    total_amount["total_residual"] += move_line["amount_residual"]
                    total_amount["total_amount_pending_on_receivables"] += move_line["amount_pending_on_receivables"]
                    if not invoice_date_due_at or not move_line['date_maturity'] or datetime.strptime(move_line['date_maturity'],
                                                                      '%d/%m/%Y') <= datetime.strptime(
                            invoice_date_due_at, '%Y-%m-%d'):
                        total_amount[account_id]["original_pre_maturity"] += move_line['original']
                        total_amount[account_id][partner_id]["original_pre_maturity"] += move_line['original']
                        total_amount[account_id]["residual_pre_maturity"] += move_line['amount_residual']
                        total_amount[account_id][partner_id]["residual_pre_maturity"] += move_line['amount_residual']
                        total_amount[account_id]["amount_pending_on_receivables_pre_maturity"] += move_line['amount_pending_on_receivables']
                        total_amount[account_id][partner_id]["amount_pending_on_receivables_pre_maturity"] += move_line['amount_pending_on_receivables']
                        total_amount["total_original_pre_maturity"] += move_line['original']
                        total_amount["total_residual_pre_maturity"] += move_line['amount_residual']
                        total_amount["total_amount_pending_on_receivables_pre_maturity"] += move_line['amount_pending_on_receivables']
                    else:
                        total_amount[account_id]["original_post_maturity"] += move_line['original']
                        total_amount[account_id][partner_id]["original_post_maturity"] += move_line['original']
                        total_amount[account_id]["residual_post_maturity"] += move_line['amount_residual']
                        total_amount[account_id][partner_id]["residual_post_maturity"] += move_line['amount_residual']
                        total_amount[account_id]["amount_pending_on_receivables_post_maturity"] += move_line['amount_pending_on_receivables']
                        total_amount[account_id][partner_id]["amount_pending_on_receivables_post_maturity"] += move_line['amount_pending_on_receivables']
                        total_amount["total_original_post_maturity"] += move_line['original']
                        total_amount["total_residual_post_maturity"] += move_line['amount_residual']
                        total_amount["total_amount_pending_on_receivables_post_maturity"] += move_line['amount_pending_on_receivables']
        return total_amount

    def _get_report_values(self, docids, data):
        wizard_id = data["wizard_id"]
        company = self.env["res.company"].browse(data["company_id"])
        company_id = data["company_id"]
        account_ids = data["account_ids"]
        partner_ids = data["partner_ids"]
        date_at = data["date_at"]
        date_at_object = datetime.strptime(date_at, "%Y-%m-%d").date()
        date_from = data["date_from"]
        date_from_object = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else False
        only_posted_moves = data["only_posted_moves"]
        show_partner_details = data["show_partner_details"]
        invoice_date_due_at = data["invoice_date_due_at"]
        invoice_date_due_at_object = datetime.strptime(data["invoice_date_due_at"], "%Y-%m-%d").date() if data["invoice_date_due_at"] else False

        (
            move_lines_data,
            partners_data,
            journals_data,
            accounts_data,
            open_items_move_lines_data,
        ) = self._get_data_custom(
            account_ids,
            partner_ids,
            date_at_object,
            only_posted_moves,
            company_id,
            date_from,
            invoice_date_due_at,
        )

        total_amount = self._calculate_amounts_custom(open_items_move_lines_data, invoice_date_due_at)
        open_items_move_lines_data = self._order_open_items_by_date(
            open_items_move_lines_data, show_partner_details
        )
        return {
            "doc_ids": [wizard_id],
            "doc_model": "open.items.report.wizard",
            "docs": self.env["open.items.report.wizard"].browse(wizard_id),
            "foreign_currency": data["foreign_currency"],
            "show_partner_details": data["show_partner_details"],
            "company_name": company.display_name,
            "company_currency": company.currency_id,
            "currency_name": company.currency_id.name,
            "date_at": date_at_object.strftime("%d/%m/%Y"),
            "hide_account_at_0": data["hide_account_at_0"],
            "target_move": data["target_move"],
            "journals_data": journals_data,
            "partners_data": partners_data,
            "accounts_data": accounts_data,
            "total_amount": total_amount,
            "Open_Items": open_items_move_lines_data,
            "date_maturity_at": invoice_date_due_at,
            "date_from": date_from_object.strftime("%d/%m/%Y") if date_from else False,
            "invoice_date_due_at": invoice_date_due_at_object.strftime("%d/%m/%Y") if invoice_date_due_at else False,
        }