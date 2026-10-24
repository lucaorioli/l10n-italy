from datetime import datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


def _get_financial_statement_line_amount(fs_lines, line_code):
    for line in fs_lines:
        if line["code"] == line_code:
            return line["amount"]


@tagged("-at_install", "post_install")
class TestFinancialStatementEU(TransactionCase):
    def setUp(self):
        # add env on cls and many other things
        super().setUp()

    def _find_or_create_account_account(
        self, company_id, code, name, code_fs_eu, account_type="income_other"
    ):
        acc_id = self.env["account.account"].search(
            [("company_ids", "in", company_id), ("code", "=", code)]
        )
        if not acc_id:
            acc_id = self.env["account.account"].create(
                {
                    "code": code,
                    "name": name,
                    "account_type": account_type,
                    "reconcile": account_type
                    in ("income_other", "asset_receivable", "liability_payable"),
                }
            )
        id_fs_eu = (
            self.env["financial.statement.eu"].search([("code", "=", code_fs_eu)]).id
        )
        if (not acc_id.financial_statement_eu_debit_id) or (
            acc_id.financial_statement_eu_debit_id.id != id_fs_eu
        ):
            self.env[
                "financial.statement.eu"
            ].financial_statement_eu_account_association(code, id_fs_eu, False, True)
        return acc_id

    def _add_move(self, company_id, ref, journal, date, line_list):
        lines = []
        for line in line_list:
            acc_id = self._find_or_create_account_account(
                company_id,
                line["code"],
                line["name"],
                line["bal_eu"],
                line.get("type", "income_other"),
            )
            if acc_id:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "debit": line["debit"],
                            "credit": line["credit"],
                            "account_id": acc_id.id,
                        },
                    )
                )

        move_vals = {
            "ref": ref,
            "journal_id": journal.id,
            "date": date,
            "line_ids": lines,
        }
        move = self.env["account.move"].create(move_vals)
        move.action_post()

    def _get_financial_statement_values(
        self, date_start, date_end, values_precision, schema="ordinary"
    ):
        wiz_financial_statement_eu = self.env["financial.statement.eu.wizard"].create(
            {
                "date_from": date_start,
                "date_to": date_end,
                "values_precision": values_precision,
                "hide_acc_amount_0": True,
                "only_posted_move": True,
                "ignore_closing_move": True,
                "schema": schema,
            }
        )
        form_data = wiz_financial_statement_eu.get_data()
        return self.env[
            "report.l10n_it_financial_statement_eu.fseu_html_report"
        ]._get_report_values(wiz_financial_statement_eu, data=form_data)

    def test_financial_statement_eu_1(self):
        company_id = self.env.company.id
        journal = self.env["account.journal"].search(
            [("company_id", "=", company_id)], limit=1
        )
        self._add_move(
            company_id,
            "vendita a cliente",
            journal,
            datetime(2023, 3, 1).date(),
            (
                {
                    "code": "150100",
                    "name": "crediti v/clienti",
                    "bal_eu": "PA.B11a",
                    "debit": 37.52,
                    "credit": 0,
                },
                {
                    "code": "260100",
                    "name": "IVA n/debito",
                    "bal_eu": "PP.DBa",
                    "debit": 0,
                    "credit": 6.77,
                },
                {
                    "code": "310100",
                    "name": "merci c/vendite",
                    "bal_eu": "E.A1",
                    "debit": 0,
                    "credit": 30.75,
                },
            ),
        )
        self._add_move(
            company_id,
            "incasso da cliente",
            journal,
            datetime(2023, 4, 5).date(),
            (
                {
                    "code": "182001",
                    "name": "Banca",
                    "bal_eu": "PA.C41",
                    "debit": 37.52,
                    "credit": 0,
                },
                {
                    "code": "150100",
                    "name": "crediti v/clienti",
                    "bal_eu": "PA.B11a",
                    "debit": 0,
                    "credit": 37.52,
                },
            ),
        )
        self._add_move(
            company_id,
            "giroconto per generare un delta nel PATRIMONIALE "
            + "su bilancio UE arrotondato alla unità",
            journal,
            datetime(2023, 4, 1).date(),
            (
                {
                    "code": "110100",
                    "name": "Costi di impianto",
                    "bal_eu": "PA.B11a",
                    "debit": 100.10,
                    "credit": 0,
                },
                {
                    "code": "110600",
                    "name": "Software",
                    "bal_eu": "PA.B13a",
                    "debit": 200.20,
                    "credit": 0,
                },
                {
                    "code": "110800",
                    "name": "Avviamento",
                    "bal_eu": "PA.B15a",
                    "debit": 300.30,
                    "credit": 0,
                },
                {
                    "code": "120500",
                    "name": "macchine d'ufficio",
                    "bal_eu": "PA.B24a",
                    "debit": 399.40,
                    "credit": 0,
                },
                {
                    "code": "210100",
                    "name": "Patrimonio netto",
                    "bal_eu": "PP.A1",
                    "debit": 0,
                    "credit": 1000,
                },
            ),
        )
        self._add_move(
            company_id,
            "giroconto per generare un delta nel CONTO ECONOMICO "
            + "su bilancio UE arrotondato alla unità",
            journal,
            datetime(2023, 4, 1).date(),
            (
                {
                    "code": "410100",
                    "name": "merci c/acquisti",
                    "bal_eu": "E.B1",
                    "debit": 100.10,
                    "credit": 0,
                },
                {
                    "code": "411100",
                    "name": "ribassi e abbuoni attivi",
                    "bal_eu": "E.B2",
                    "debit": 200.20,
                    "credit": 0,
                },
                {
                    "code": "430100",
                    "name": "fitti passivi",
                    "bal_eu": "E.B3",
                    "debit": 300.30,
                    "credit": 0,
                },
                {
                    "code": "440100",
                    "name": "salari e stipendi",
                    "bal_eu": "E.B41",
                    "debit": 399.40,
                    "credit": 0,
                },
                {
                    "code": "310300",
                    "name": "rimborsi spese di vendita",
                    "bal_eu": "E.A511",
                    "debit": 0,
                    "credit": 1000,
                },
            ),
        )
        # checks with decimals
        bal_values = self._get_financial_statement_values(
            datetime(2023, 1, 1).date(), datetime(2023, 12, 31).date(), "d"
        )
        self.assertNotEqual(bal_values.get("financial_statement_state"), "UNBALANCED")
        bal_lines = bal_values.get("financial_statement_eu_lines")
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "PA.C21a"), 0)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "PA"), 1037.52)
        self.assertEqual(
            _get_financial_statement_line_amount(bal_lines, "E.A"), 1030.75
        )
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "E=F"), 30.75)
        # checks without decimals
        bal_values = self._get_financial_statement_values(
            datetime(2023, 1, 1).date(), datetime(2023, 12, 31).date(), "u"
        )
        self.assertNotEqual(bal_values.get("financial_statement_state"), "UNBALANCED")
        bal_lines = bal_values.get("financial_statement_eu_lines")
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "PA.C21a"), 0)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "PA"), 1037)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "E.A"), 1030)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "E=F"), 31)

    def test_financial_statement_eu_abbreviated(self):
        """Abbreviated schema: balance sheet up to the roman numerals, with
        receivables and payables split by due date, and the grouped lines of
        the income statement."""
        company_id = self.env.company.id
        journal = self.env["account.journal"].search(
            [("company_id", "=", company_id)], limit=1
        )
        self._add_move(
            company_id,
            "vendita",
            journal,
            datetime(2023, 3, 1).date(),
            (
                {
                    "code": "150100",
                    "type": "asset_receivable",
                    "name": "crediti v/clienti",
                    "bal_eu": "PA.C21a",
                    "debit": 122,
                    "credit": 0,
                },
                {
                    "code": "260100",
                    "type": "liability_current",
                    "name": "IVA n/debito",
                    "bal_eu": "PP.DBa",
                    "debit": 0,
                    "credit": 22,
                },
                {
                    "code": "310100",
                    "type": "income",
                    "name": "merci c/vendite",
                    "bal_eu": "E.A1",
                    "debit": 0,
                    "credit": 100,
                },
            ),
        )
        self._add_move(
            company_id,
            "personale",
            journal,
            datetime(2023, 4, 1).date(),
            (
                {
                    "code": "440100",
                    "type": "expense",
                    "name": "salari e stipendi",
                    "bal_eu": "E.B41",
                    "debit": 50,
                    "credit": 0,
                },
                {
                    "code": "440300",
                    "type": "expense",
                    "name": "trattamento di fine rapporto",
                    "bal_eu": "E.B43",
                    "debit": 10,
                    "credit": 0,
                },
                {
                    "code": "182001",
                    "type": "asset_cash",
                    "name": "Banca",
                    "bal_eu": "PA.C41",
                    "debit": 0,
                    "credit": 60,
                },
            ),
        )
        date_from, date_to = datetime(2023, 1, 1).date(), datetime(2023, 12, 31).date()
        bal_values = self._get_financial_statement_values(
            date_from, date_to, "d", schema="abbreviated"
        )
        bal_lines = bal_values.get("financial_statement_eu_lines")
        codes = [line["code"] for line in bal_lines]
        self.assertNotIn("PA.C21a", codes)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "PA.C2"), 122)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "PA=C2E"), 122)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "PA=C2O"), 0)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "PP=DE"), 22)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "E.B41"), 50)
        self.assertEqual(_get_financial_statement_line_amount(bal_lines, "E=B4cde"), 10)
        receivables = next(line for line in bal_lines if line["code"] == "PA.C2")
        self.assertEqual([acc["code"] for acc in receivables["accounts"]], ["150100"])
        # The lines of the abbreviated schema only are not in the ordinary one
        bal_values = self._get_financial_statement_values(date_from, date_to, "d")
        codes = [
            line["code"] for line in bal_values.get("financial_statement_eu_lines")
        ]
        self.assertIn("PA.C21a", codes)
        self.assertNotIn("PA=C2E", codes)
