# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    'name': 'Account Payment Document',
    'summary': "Create documents to group move lines, then import these documents to payment orders.",
    'version': '13.0.1.2.0',
    'license': 'AGPL-3',
    'author': "Domatix",
    'website': 'https://domatix.com/',
    'category': 'Banking addons',
    'depends': [
        'account', 'account_payment_order', 'l10n_es_account_banking_sepa_fsdd', 'account_payment_return'
    ],
    'data': [
        'security/payment_security.xml',
        'security/ir.model.access.csv',
        'wizard/account_document_line_create_view.xml',
        'wizard/account_payment_line_create_view.xml',
        'views/account_move_views.xml',
        'views/account_payment_order.xml',
        'views/account_payment_document.xml',
        'views/account_payment_mode_views.xml',
        'views/account_document_line.xml',
        'views/account_move_views.xml',
        'views/account.xml',
        'reports/account_payment_report.xml',
        'reports/account_payment.xml',
        'data/ir_cron.xml',
    ],
    'qweb': [
        "static/src/xml/account_reconciliation.xml"
    ],
    'installable': True,
}
