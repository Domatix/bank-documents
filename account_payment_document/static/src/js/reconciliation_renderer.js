odoo.define('account_payment_document.ReconciliationRenderer', function (require){
"use strict";

// var FieldManagerMixin = require('web.FieldManagerMixin');
var ReconciliationRenderer = require('account.ReconciliationRenderer');
var relational_fields = require('web.relational_fields');
var basic_fields = require('web.basic_fields');
var core = require('web.core');
var qweb = core.qweb;
var _t = core._t;

ReconciliationRenderer.LineRenderer.include({

  /**
 * create account_id, tax_id, analytic_account_id, analytic_tag_ids, label and amount fields
 * @override
 * @private
 * @param {object} state - statement line
 */
 _renderCreate: function (state) {
     var self = this;
     return this.model.makeRecord('account.bank.statement.line', [{
         relation: 'account.account',
         type: 'many2one',
         name: 'account_id',
         domain: [['company_id', '=', state.st_line.company_id], ['deprecated', '=', false]],
     }, {
         relation: 'account.journal',
         type: 'many2one',
         name: 'journal_id',
         domain: [['company_id', '=', state.st_line.company_id]],
     }, {
         relation: 'account.tax',
         type: 'many2many',
         name: 'tax_ids',
         domain: [['company_id', '=', state.st_line.company_id]],
     }, {
         relation: 'account.analytic.account',
         type: 'many2one',
         name: 'analytic_account_id',
     }, {
         relation: 'account.analytic.tag',
         type: 'many2many',
         name: 'analytic_tag_ids',
     }, {
         type: 'boolean',
         name: 'force_tax_included',
     }, {
         type: 'char',
         name: 'label',
     }, {
         type: 'float',
         name: 'amount',
     }, {
         type: 'char', //TODO is it a bug or a feature when type date exists ?
         name: 'date',
     }, {
         relation: 'account.payment.order',
         type: 'many2one',
         name: 'order_id',
         domain: [['state', '=', 'uploaded']],
     }, {
         relation: 'account.payment.document',
         type: 'many2one',
         name: 'document_id',
         domain: [['state', '=', 'open']],
     }, {
         type: 'boolean',
         name: 'to_check',
     }], {
         account_id: {
             string: _t("Account"),
         },
         label: {string: _t("Label")},
         amount: {string: _t("Account")},
     }).then(function (recordID) {
         self.handleCreateRecord = recordID;
         var record = self.model.get(self.handleCreateRecord);

         self.fields.account_id = new relational_fields.FieldMany2One(self,
             'account_id', record, {mode: 'edit', attrs: {can_create:false}});

         self.fields.journal_id = new relational_fields.FieldMany2One(self,
             'journal_id', record, {mode: 'edit'});

         self.fields.tax_ids = new relational_fields.FieldMany2ManyTags(self,
             'tax_ids', record, {mode: 'edit', additionalContext: {append_type_to_tax_name: true}});

         self.fields.analytic_account_id = new relational_fields.FieldMany2One(self,
             'analytic_account_id', record, {mode: 'edit'});

         self.fields.analytic_tag_ids = new relational_fields.FieldMany2ManyTags(self,
             'analytic_tag_ids', record, {mode: 'edit'});

         self.fields.force_tax_included = new basic_fields.FieldBoolean(self,
             'force_tax_included', record, {mode: 'edit'});

         self.fields.label = new basic_fields.FieldChar(self,
             'label', record, {mode: 'edit'});

         self.fields.amount = new basic_fields.FieldFloat(self,
             'amount', record, {mode: 'edit'});

         self.fields.date = new basic_fields.FieldDate(self,
             'date', record, {mode: 'edit'});

         self.fields.to_check = new basic_fields.FieldBoolean(self,
             'to_check', record, {mode: 'edit'});

         self.fields.document_id = new relational_fields.FieldMany2One(self,
             'document_id', record, {mode: 'edit'});

         self.fields.order_id = new relational_fields.FieldMany2One(self,
             'order_id', record, {mode: 'edit'});

         var $create = $(qweb.render("reconciliation.line.create.document", {'state': state, 'group_tags': self.group_tags, 'group_acc': self.group_acc}));
         self.fields.account_id.appendTo($create.find('.create_account_id .o_td_field'))
             .then(addRequiredStyle.bind(self, self.fields.account_id));
         self.fields.journal_id.appendTo($create.find('.create_journal_id .o_td_field'));
         self.fields.tax_ids.appendTo($create.find('.create_tax_id .o_td_field'));
         self.fields.analytic_account_id.appendTo($create.find('.create_analytic_account_id .o_td_field'));
         self.fields.analytic_tag_ids.appendTo($create.find('.create_analytic_tag_ids .o_td_field'));
         self.fields.force_tax_included.appendTo($create.find('.create_force_tax_included .o_td_field'));
         self.fields.label.appendTo($create.find('.create_label .o_td_field'))
             .then(addRequiredStyle.bind(self, self.fields.label));
         self.fields.amount.appendTo($create.find('.create_amount .o_td_field'))
             .then(addRequiredStyle.bind(self, self.fields.amount));
         self.fields.date.appendTo($create.find('.create_date .o_td_field'));
         self.fields.to_check.appendTo($create.find('.create_to_check .o_td_field'));
         self.fields.document_id.appendTo($create.find('.create_document_id .o_td_field'));
         self.fields.order_id.appendTo($create.find('.create_order_id .o_td_field'));
         self.$('.create').append($create);

         function addRequiredStyle(widget) {
             widget.$el.addClass('o_required_modifier');
         }
     });
 },

});
});
