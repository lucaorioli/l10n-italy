# Copyright 2022 MKT srl
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import operator

from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)


class FinancialStatementEU(models.Model):
    _name = "financial.statement.eu"
    _description = "Financial statement EU line"
    _rec_names_search = ["complete_name"]
    _rec_name = "complete_name"
    _order = "sequence, id"
    zone_bal = fields.Selection(
        [
            ("PA", "Assets"),
            ("PP", "Liabilities"),
            ("EC", "Income statement"),
            ("--", "Ignore"),
        ],
        string="Zone",
        required=True,
    )
    code = fields.Char(size=8)
    name = fields.Char(
        string="Description",
    )
    long_desc = fields.Char(
        string="Complete Description",
    )
    sign_calculation = fields.Selection(
        selection=[
            ("-", "Subtract"),
            ("", "Add"),
        ],
        string="Sign (calc)",
    )
    sign_display = fields.Selection(
        selection=[
            ("+", "Positive"),
            ("-", "Negative"),
        ],
        string="Sign (view)",
    )
    sequence = fields.Integer(
        string="#",
        required=False,
    )
    ordinary = fields.Boolean(
        string="Ordinary schema",
        default=True,
        help="Line of the ordinary financial statements (art. 2424-2425 c.c.)",
    )
    abbreviated = fields.Boolean(
        string="Abbreviated schema",
        help="Line of the abbreviated financial statements (art. 2435-bis c.c.)",
    )
    sum_codes = fields.Char(
        string="Sum of lines",
        help="Comma separated codes of the lines summed by a line of the "
        "abbreviated schema only, such as receivables due within the next year",
    )
    tag_xbrl = fields.Char(
        string="Name XBRL",
    )
    parent_id = fields.Many2one(
        comodel_name="financial.statement.eu",
        string="Parent",
        index=True,
    )
    child_ids = fields.One2many(
        comodel_name="financial.statement.eu",
        inverse_name="parent_id",
        string="Childs",
    )
    complete_name = fields.Char(
        compute="_compute_complete_name", store=True, recursive=True
    )

    def get_parent_path(self):
        self.ensure_one()
        if self.parent_id:
            line = self.parent_id.get_parent_path()
        else:
            line = ""
        return line + self.name + " / "

    @api.depends("code", "name", "parent_id", "parent_id.complete_name")
    def _compute_complete_name(self):
        for line in self:
            if line.parent_id:
                p = line.parent_id.get_parent_path()
            else:
                p = ""
            line.complete_name = f"[{line.code}] {p}{line.name}"

    @api.constrains("code", "zone_bal")
    def _check_code_zone(self):
        for line in self:
            if (line.zone_bal == "PA") and (not line.code.startswith("PA")):
                raise ValidationError(self.env._("ASSETS codes must starting by PA"))
            elif (line.zone_bal == "PP") and (not line.code.startswith("PP")):
                raise ValidationError(
                    self.env._("LIABILITIES codes must starting by PP")
                )
            elif (line.zone_bal == "EC") and (not line.code.startswith("E")):
                raise ValidationError(
                    self.env._("INCOME STATEMENT codes must starting by E")
                )

    @api.model
    def financial_statement_eu_account_association(
        self,
        acc_code,
        debit_fse_id,
        credit_fse_id,
        force_update,
    ):
        # All companies: accounts are shared, the association must reach each one
        companies = self.env["res.company"].search([])  # pylint: disable=no-search-all
        for company in companies:
            acc_ids = (
                self.env["account.account"]
                .with_company(company)
                .search(
                    [
                        ("code", "=ilike", acc_code),
                    ]
                )
            )
            for acc_id in acc_ids:
                if (
                    (not acc_id.financial_statement_eu_debit_id)
                    and (not acc_id.financial_statement_eu_credit_id)
                ) or force_update:
                    if (acc_id.financial_statement_eu_debit_id.id != debit_fse_id) or (
                        acc_id.financial_statement_eu_credit_id.id != credit_fse_id
                    ):
                        acc_id.write(
                            {
                                "financial_statement_eu_debit_id": debit_fse_id,
                                "financial_statement_eu_credit_id": credit_fse_id,
                            }
                        )

    @api.model
    def financial_statement_eu_account_assoc_code(
        self,
        acc_code,
        debit_financial_statement_eu_code,
        credit_financial_statement_eu_code,
    ):
        if debit_financial_statement_eu_code:
            debit_fse_id = self.search(
                [("code", "=", debit_financial_statement_eu_code)]
            )
        else:
            debit_fse_id = False
        if credit_financial_statement_eu_code:
            credit_fse_id = self.search(
                [("code", "=", credit_financial_statement_eu_code)]
            )
        else:
            credit_fse_id = False
        if debit_fse_id or credit_fse_id:
            self.financial_statement_eu_account_association(
                acc_code,
                debit_fse_id,
                credit_fse_id,
                False,
            )

    def cal_financial_statement_eu_line_amount(
        self, financial_statement_eu_lines, code
    ):
        total_amount = 0
        rounded_amount = 0
        financial_statement_eu_child_ids = self.env["financial.statement.eu"].search(
            [
                (
                    "parent_id",
                    "=",
                    financial_statement_eu_lines[code]["financial_statement_line"].id,
                )
            ]
        )
        for child in financial_statement_eu_child_ids:
            if child.child_ids:
                self.cal_financial_statement_eu_line_amount(
                    financial_statement_eu_lines, child.code
                )
            if child.sign_calculation == "-":
                rounded_amount -= financial_statement_eu_lines[child.code][
                    "rounded_amount"
                ]
                total_amount -= financial_statement_eu_lines[child.code]["total_amount"]
            else:
                rounded_amount += financial_statement_eu_lines[child.code][
                    "rounded_amount"
                ]
                total_amount += financial_statement_eu_lines[child.code]["total_amount"]
        financial_statement_eu_lines[code]["rounded_amount"] = tools.float_round(
            rounded_amount, 2
        )
        financial_statement_eu_lines[code]["total_amount"] = total_amount

    def add_calc_type_domain(self, domain, calc_type, financial_statement_eu_id):
        if calc_type == "d":
            domain.append(
                ("financial_statement_eu_debit_id", "=", financial_statement_eu_id)
            )
        elif calc_type == "c":
            domain.append(
                ("financial_statement_eu_credit_id", "=", financial_statement_eu_id)
            )
        elif calc_type == "non_assoc":
            domain.append(("financial_statement_eu_debit_id", "=", False))
            domain.append(("financial_statement_eu_credit_id", "=", False))

    def get_account_list_amount(
        self,
        company_id,
        currency_id,
        date_from,
        date_to,
        only_posted_move,
        hide_acc_amount_0,
        ignore_closing_move,
        calc_type,
        financial_statement_eu_id,
        sign_display,
        financial_statement_line_amount,
        account_list,
    ):
        currency_precision = currency_id.decimal_places
        domain = []
        domain.append(("company_ids", "in", company_id))
        self.add_calc_type_domain(domain, calc_type, financial_statement_eu_id)
        accounts = self.env["account.account"].search(domain, order="code")
        aml_model = self.env["account.move.line"]
        for account in accounts:
            acc_credit_id = account.financial_statement_eu_credit_id
            acc_debit_id = account.financial_statement_eu_debit_id
            domain = [
                ("company_id", "=", company_id),
                ("account_id", "=", account.id),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ]
            if only_posted_move:
                domain.append(("move_id.state", "=", "posted"))
            if ignore_closing_move:
                domain.append(("move_id.closing_type", "!=", "closing"))
                domain.append(("move_id.closing_type", "!=", "loss_profit"))
            amls = aml_model._read_group(
                domain, groupby=["account_id"], aggregates=["debit:sum", "credit:sum"]
            )
            if amls:
                for _account, debit, credit in amls:
                    acc_amount = tools.float_round(debit - credit, currency_precision)
                    if (
                        (calc_type == "non_assoc")
                        or (
                            (calc_type == "d")  # debit
                            and (
                                (currency_id.compare_amounts(acc_amount, 0) >= 0)
                                or (not acc_credit_id)
                            )
                        )
                        or (
                            (calc_type == "c")  # credit
                            and (
                                (currency_id.compare_amounts(acc_amount, 0) == -1)
                                or (not acc_debit_id)
                            )
                        )
                    ):
                        if sign_display == "-":
                            acc_amount = -acc_amount
                        financial_statement_line_amount = (
                            financial_statement_line_amount + acc_amount
                        )
                        if (not hide_acc_amount_0) or (acc_amount != 0):
                            account_list.append(
                                {
                                    "code": account.code,
                                    "desc": account.name,
                                    "amount": acc_amount,
                                }
                            )
            elif not hide_acc_amount_0:
                account_list.append(
                    {
                        "code": account.code,
                        "desc": account.name,
                        "amount": 0,
                    }
                )
        return financial_statement_line_amount

    def _get_hidden_leaves(self):
        """The detail lines summed by this line and not shown in the
        abbreviated schema, down to the first shown children."""
        self.ensure_one()
        leaves = self.browse()
        for child in self.child_ids.filtered(lambda line: not line.abbreviated):
            leaves |= child._get_hidden_leaves() if child.child_ids else child
        return leaves

    def _prepare_abbreviated(self, financial_statement_eu_lines, form_data):
        """Abbreviated schema: the lines that only exist there are sums of other
        lines, and a line whose details are not shown lists their accounts."""
        if form_data.get("schema") != "abbreviated":
            return
        for line in financial_statement_eu_lines.values():
            item = line["financial_statement_line"]
            if item.sum_codes:
                codes = [
                    code.strip()
                    for code in item.sum_codes.split(",")
                    if code.strip() in financial_statement_eu_lines
                ]
                for key in ("total_amount", "rounded_amount"):
                    line[key] = sum(
                        financial_statement_eu_lines[code][key] for code in codes
                    )
                line["rounded_amount"] = tools.float_round(line["rounded_amount"], 2)
            elif item.abbreviated and item.child_ids:
                line["account_list"] = sorted(
                    (
                        account
                        for leaf in item._get_hidden_leaves()
                        for account in financial_statement_eu_lines[leaf.code][
                            "account_list"
                        ]
                    ),
                    key=operator.itemgetter("code"),
                )

    def _filter_schema(self, report_lines, form_data):
        """The lines of the chosen schema, ordinary or abbreviated."""
        schema = (
            "abbreviated" if form_data.get("schema") == "abbreviated" else "ordinary"
        )
        codes = set(self.search([(schema, "=", True)]).mapped("code"))
        return [line for line in report_lines if line["code"] in codes]

    def round_bal_val(self, val, precision):
        if precision == "u":
            return tools.float_round(val, 0)
        elif precision == "d":
            return tools.float_round(val, 2)
        else:
            return val

    def cal_financial_statement_eu_data(self, form_data):
        financial_statement_eu_lines = {}
        company_id = form_data["company_id"][0]
        currency_id = self.env["res.currency"].browse(form_data["currency_id"][0])
        date_from = form_data["date_from"]
        date_to = form_data["date_to"]
        only_posted_move = form_data["only_posted_move"]
        hide_acc_amount_0 = form_data["hide_acc_amount_0"]
        ignore_closing_move = form_data["ignore_closing_move"]
        if ignore_closing_move:
            if not self.env["account.move"].fields_get(allfields=["closing_type"]):
                ignore_closing_move = False
        # Every line of the statement is computed, the whole tree is needed
        financial_statement_eu_ids = self.search([])  # pylint: disable=no-search-all
        for item in financial_statement_eu_ids:
            financial_statement_eu_amount = 0
            account_list = []
            if not item.child_ids:
                calcs = ["d", "c"]  # d=debit c=credit
                for calc_type in calcs:
                    financial_statement_eu_amount = self.get_account_list_amount(
                        company_id,
                        currency_id,
                        date_from,
                        date_to,
                        only_posted_move,
                        hide_acc_amount_0,
                        ignore_closing_move,
                        calc_type,
                        item.id,
                        item.sign_display,
                        financial_statement_eu_amount,
                        account_list,
                    )
            account_list.sort(key=operator.itemgetter("code"))

            financial_statement_eu_amount_rounded = self.round_bal_val(
                financial_statement_eu_amount, form_data["values_precision"]
            )
            financial_statement_eu_lines[item.code] = {
                "financial_statement_line": item,
                "rounded_amount": financial_statement_eu_amount_rounded,
                "total_amount": financial_statement_eu_amount,
                "account_list": account_list,
            }
        self.cal_financial_statement_eu_line_amount(financial_statement_eu_lines, "E.A")
        self.cal_financial_statement_eu_line_amount(financial_statement_eu_lines, "E.B")
        self.cal_financial_statement_eu_line_amount(financial_statement_eu_lines, "E.C")
        self.cal_financial_statement_eu_line_amount(financial_statement_eu_lines, "E.D")
        self.cal_financial_statement_eu_line_amount(financial_statement_eu_lines, "E.F")
        financial_statement_eu_lines["E=B"]["rounded_amount"] = (
            financial_statement_eu_lines["E.A"]["rounded_amount"]
            - financial_statement_eu_lines["E.B"]["rounded_amount"]
        )
        financial_statement_eu_lines["E=B"]["total_amount"] = (
            financial_statement_eu_lines["E.A"]["total_amount"]
            - financial_statement_eu_lines["E.B"]["total_amount"]
        )
        financial_statement_eu_lines["E=E"]["rounded_amount"] = (
            financial_statement_eu_lines["E=B"]["rounded_amount"]
            + financial_statement_eu_lines["E.C"]["rounded_amount"]
            + financial_statement_eu_lines["E.D"]["rounded_amount"]
        )
        financial_statement_eu_lines["E=E"]["total_amount"] = (
            financial_statement_eu_lines["E=B"]["total_amount"]
            + financial_statement_eu_lines["E.C"]["total_amount"]
            + financial_statement_eu_lines["E.D"]["total_amount"]
        )
        financial_statement_eu_lines["E=F"]["rounded_amount"] = (
            financial_statement_eu_lines["E=E"]["rounded_amount"]
            - financial_statement_eu_lines["E.F"]["rounded_amount"]
        )
        financial_statement_eu_lines["E=F"]["total_amount"] = (
            financial_statement_eu_lines["E=E"]["total_amount"]
            - financial_statement_eu_lines["E.F"]["total_amount"]
        )
        delta_ef = (
            self.round_bal_val(
                financial_statement_eu_lines["E=F"]["total_amount"],
                form_data["values_precision"],
            )
            - financial_statement_eu_lines["E=F"]["rounded_amount"]
        )
        if delta_ef != 0:
            financial_statement_eu_lines["E=A512"]["rounded_amount"] = delta_ef
            financial_statement_eu_lines["E.A51"]["rounded_amount"] += delta_ef
            financial_statement_eu_lines["E.A5"]["rounded_amount"] += delta_ef
            financial_statement_eu_lines["E.A"]["rounded_amount"] += delta_ef
            financial_statement_eu_lines["E=B"]["rounded_amount"] += delta_ef
            financial_statement_eu_lines["E=E"]["rounded_amount"] += delta_ef
            financial_statement_eu_lines["E=F"]["rounded_amount"] += delta_ef

        financial_statement_eu_lines["PP=A9"]["rounded_amount"] = (
            financial_statement_eu_lines["E=F"]["rounded_amount"]
        )
        financial_statement_eu_lines["PP=A9"]["total_amount"] = (
            financial_statement_eu_lines["E=F"]["total_amount"]
        )
        self.cal_financial_statement_eu_line_amount(financial_statement_eu_lines, "PA")
        self.cal_financial_statement_eu_line_amount(financial_statement_eu_lines, "PP")
        financial_statement_eu_lines["PP=A7j2"]["total_amount"] = (
            financial_statement_eu_lines["PA"]["rounded_amount"]
            - financial_statement_eu_lines["PP"]["rounded_amount"]
        ) - (
            financial_statement_eu_lines["PA"]["total_amount"]
            - financial_statement_eu_lines["PP"]["total_amount"]
        )

        financial_statement_eu_lines["PP=A7j2"]["rounded_amount"] = self.round_bal_val(
            financial_statement_eu_lines["PP=A7j2"]["total_amount"],
            form_data["values_precision"],
        )
        self.cal_financial_statement_eu_line_amount(financial_statement_eu_lines, "PP")
        self._prepare_abbreviated(financial_statement_eu_lines, form_data)
        log_warnings = ""
        acc_ignore = ""
        financial_statement_eu_lines_report_data = []
        for line in financial_statement_eu_lines:
            if (
                financial_statement_eu_lines[line]["financial_statement_line"].zone_bal
                != "--"
            ):
                financial_statement_eu_lines_report_data.append(
                    {
                        "code": financial_statement_eu_lines[line][
                            "financial_statement_line"
                        ].code,
                        "desc": financial_statement_eu_lines[line][
                            "financial_statement_line"
                        ].long_desc,
                        "amount": financial_statement_eu_lines[line]["rounded_amount"],
                        "accounts": financial_statement_eu_lines[line]["account_list"],
                    }
                )
            else:
                for acc in financial_statement_eu_lines[line]["account_list"]:
                    if acc["amount"] != 0:
                        acc_ignore += (
                            "   "
                            + acc["code"]
                            + " "
                            + acc["desc"]
                            + ": "
                            + formatLang(
                                self.env, acc["amount"], currency_obj=currency_id
                            )
                            + "\n"
                        )
        if acc_ignore != "":
            log_warnings += (
                self.env._("There are accounts to ignore but with non-zero amount:")
                + "\n"
                + acc_ignore
            )
        financial_statement_state = "OK"
        log_env = self.env["financial.statement.eu.log"]
        log_env.search(
            [("financial_statement_id", "=", form_data["id"])]
        ).unlink()  # clear log
        unlinked_account = []
        tot = 0
        self.get_account_list_amount(
            company_id,
            currency_id,
            date_from,
            date_to,
            only_posted_move,
            hide_acc_amount_0,
            ignore_closing_move,
            "non_assoc",
            False,
            "",
            tot,
            unlinked_account,
        )
        if (
            financial_statement_eu_lines["PA"]["rounded_amount"]
            != financial_statement_eu_lines["PP"]["rounded_amount"]
        ):
            financial_statement_state = "UNBALANCED"
            log_warnings = log_warnings + self.env._(
                "Unbalanced financial statements: "
                "%(tot_assets)s (Assets) - %(tot_liabilities)s (Liabilities)"
                " = %(diff)s",
                tot_assets=formatLang(
                    self.env,
                    financial_statement_eu_lines["PA"]["rounded_amount"],
                    currency_obj=currency_id,
                ),
                tot_liabilities=formatLang(
                    self.env,
                    financial_statement_eu_lines["PP"]["rounded_amount"],
                    currency_obj=currency_id,
                ),
                diff=formatLang(
                    self.env,
                    tools.float_round(
                        financial_statement_eu_lines["PA"]["rounded_amount"]
                        - financial_statement_eu_lines["PP"]["rounded_amount"],
                        2,
                    ),
                    currency_obj=currency_id,
                ),
            )
        if len(unlinked_account) > 0:
            financial_statement_state = "UNLINKED_ACCOUNTS"
            log_warnings += (
                "\n"
                + self.env._(
                    "There are accounts not linked to any financial statement line:"
                )
                + "\n"
            )

            for acc in unlinked_account:
                account_id = (
                    self.env["account.account"]
                    .search([("code", "=", acc.get("code"))])
                    .id
                )
                log_env.create(
                    {
                        "financial_statement_id": form_data["id"],
                        "account_id": account_id,
                        "amount": acc.get("amount"),
                    }
                )
        log_warnings = log_warnings.strip()
        if log_warnings == "":
            warning_lines = []
        else:
            warning_lines = log_warnings.split("\n")
        data = {
            "form_data": form_data,
            "financial_statement_eu_lines": self._filter_schema(
                financial_statement_eu_lines_report_data, form_data
            ),
            "financial_statement_state": financial_statement_state,
            "warnings": warning_lines,
            "unlinked_account": unlinked_account,
        }
        return data


class AccountRefFinancialStatementEU(models.Model):
    _inherit = "account.account"
    financial_statement_eu_debit_id = fields.Many2one(
        "financial.statement.eu",
        string="Debit (Financial statement EU)",
        domain="[('child_ids','=',False),"
        "'|', ('code','=','PP=A9'), ('code','not like','%=%')"
        "]",
        help="Add this account in a Financial statement EU line amount DEBITS",
    )
    financial_statement_eu_credit_id = fields.Many2one(
        "financial.statement.eu",
        string="Credit (Financial statement EU)",
        domain="[('child_ids','=',False),"
        "'|', ('code','=','PP=A9'), ('code','not like', '%=%')"
        "]",
        help="Add this account in a Financial statement EU line amount CREDITS",
    )
