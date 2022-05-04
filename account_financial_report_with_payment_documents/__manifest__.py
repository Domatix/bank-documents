# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    'name': 'Account Financial Report With Payment Documents',
    'summary': "Modify the Open Items report with the account payment document upgrade.",
    'version': '13.0.1.2.0',
    'license': 'AGPL-3',
    'author': "Domatix",
    'website': 'https://domatix.com/',
    'category': 'Reports',
    'depends': [
        'account_financial_report', 'account_payment_document',
    ],
    'data': [
        'report/open_items_template.xml',
        'wizard/open_items_wizard_view.xml',
    ],
    'qweb': [
    ],
    'installable': True,
}
