odoo.define('account_payment_document.ReconciliationModel', function (require){
"use strict";

var ReconciliationModel = require('account.ReconciliationModel');

ReconciliationModel.StatementModel.include({
  quickCreateFields: ['account_id', 'amount', 'analytic_account_id', 'label', 'tax_ids', 'force_tax_included', 'analytic_tag_ids', 'to_check', 'order_id', 'document_id'],

_formatToProcessReconciliation: function (line, prop) {
  var amount = -prop.amount;
  if (prop.partial_amount) {
      amount = -prop.partial_amount;
  }

  var result = {
      name : prop.label,
      debit : amount > 0 ? amount : 0,
      credit : amount < 0 ? -amount : 0,
      tax_exigible: prop.tax_exigible,
      analytic_tag_ids: [[6, null, _.pluck(prop.analytic_tag_ids, 'id')]]
  };
  if (prop.document_id){
    result.document_id = prop.document_id.id;
  }
  if (prop.order_id){
    result.order_id = prop.order_id.id;
  }
  if (!isNaN(prop.id)) {
      result.counterpart_aml_id = prop.id;
  } else {
      result.account_id = prop.account_id.id;
      if (prop.journal_id) {
          result.journal_id = prop.journal_id.id;
      }
  }
  if (!isNaN(prop.id)) result.counterpart_aml_id = prop.id;
  if (prop.analytic_account_id) result.analytic_account_id = prop.analytic_account_id.id;
  if (prop.tax_ids && prop.tax_ids.length) result.tax_ids = [[6, null, _.pluck(prop.tax_ids, 'id')]];

  if (prop.tag_ids && prop.tag_ids.length) result.tag_ids = [[6, null, prop.tag_ids]];
  if (prop.tax_repartition_line_id) result.tax_repartition_line_id = prop.tax_repartition_line_id;
  if (prop.reconcileModelId) result.reconcile_model_id = prop.reconcileModelId
  return result;
},

});
});
