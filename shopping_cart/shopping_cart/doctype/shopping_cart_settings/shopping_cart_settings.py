# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _, msgprint
from frappe.utils import comma_and
from frappe.model.controller import DocListController
from frappe.utils.nestedset import get_ancestors_of

class ShoppingCartSetupError(frappe.ValidationError): pass

class ShoppingCartSettings(DocListController):
	def onload(self):
		self.set("__quotation_series", frappe.get_meta("Quotation").get_options("naming_series"))
	
	def validate(self):
		if self.enabled:
			self.validate_price_lists()
			self.validate_tax_masters()
			self.validate_exchange_rates_exist()
			
	def on_update(self):
		frappe.db.set_default("shopping_cart_enabled", self.get("enabled") or 0)
		frappe.db.set_default("shopping_cart_quotation_series", self.get("quotation_series"))
			
	def validate_overlapping_territories(self, parentfield, fieldname):
		# for displaying message
		doctype = self.meta.get_field(parentfield).options
		
		# specify atleast one entry in the table
		self.validate_table_has_rows(parentfield, raise_exception=ShoppingCartSetupError)
		
		territory_name_map = self.get_territory_name_map(parentfield, fieldname)
		for territory, names in territory_name_map.items():
			if len(names) > 1:
				msgprint(_("Error for") + " " + _(doctype) + ": " + comma_and(names) +
					" " + _("have a common territory") + ": " + territory,
					raise_exception=ShoppingCartSetupError)
					
		return territory_name_map
		
	def validate_price_lists(self):
		territory_name_map = self.validate_overlapping_territories("price_lists", "selling_price_list")
		
		# validate that a Shopping Cart Price List exists for the default territory as a catch all!
		price_list_for_default_territory = self.get_name_from_territory(self.default_territory, "price_lists",
			"selling_price_list")

		if not price_list_for_default_territory:
			msgprint(_("Please specify a Price List which is valid for Territory") + 
				": " + self.default_territory, raise_exception=ShoppingCartSetupError)
		
	def validate_tax_masters(self):
		self.validate_overlapping_territories("sales_taxes_and_charges_masters", 
			"sales_taxes_and_charges_master")
		
	def get_territory_name_map(self, parentfield, fieldname):
		territory_name_map = {}
		
		# entries in table
		names = [doc.get(fieldname) for doc in self.get(parentfield)]
		
		if names:
			# for condition in territory check
			parenttype = self.meta.get_field(fieldname, parentfield=parentfield).options
		
			# to validate territory overlap
			# make a map of territory: [list of names]
			# if list against each territory has more than one element, raise exception
			territory_name = frappe.db.sql("""select `territory`, `parent` 
				from `tabApplicable Territory`
				where `parenttype`=%s and `parent` in (%s)""" %
				("%s", ", ".join(["%s"]*len(names))), tuple([parenttype] + names))
		
			for territory, name in territory_name:
				territory_name_map.setdefault(territory, []).append(name)
				
				if len(territory_name_map[territory]) > 1:
					territory_name_map[territory].sort(key=lambda val: names.index(val))
		
		return territory_name_map
					
	def validate_exchange_rates_exist(self):
		"""check if exchange rates exist for all Price List currencies (to company's currency)"""
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		if not company_currency:
			msgprint(_("Please specify currency in Company") + ": " + self.company,
				raise_exception=ShoppingCartSetupError)
		
		price_list_currency_map = frappe.db.get_values("Price List", 
			[d.selling_price_list for d in self.get("price_lists")],
			"currency")
		
		# check if all price lists have a currency
		for price_list, currency in price_list_currency_map.items():
			if not currency:
				frappe.throw("%s: %s" % (_("Currency is missing for Price List"), price_list))
			
		expected_to_exist = [currency + "-" + company_currency 
			for currency in price_list_currency_map.values()
			if currency != company_currency]
			
		if expected_to_exist:
			exists = frappe.db.sql_list("""select name from `tabCurrency Exchange`
				where name in (%s)""" % (", ".join(["%s"]*len(expected_to_exist)),),
				tuple(expected_to_exist))
		
			missing = list(set(expected_to_exist).difference(exists))
		
			if missing:
				msgprint(_("Missing Currency Exchange Rates for" + ": " + comma_and(missing)),
					raise_exception=ShoppingCartSetupError)
				
	def get_name_from_territory(self, territory, parentfield, fieldname):
		name = None
		territory_name_map = self.get_territory_name_map(parentfield, fieldname)
		
		if territory_name_map.get(territory):
			name = territory_name_map.get(territory)
		else:
			territory_ancestry = self.get_territory_ancestry(territory)
			for ancestor in territory_ancestry:
				if territory_name_map.get(ancestor):
					name = territory_name_map.get(ancestor)
					break
		
		return name
				
	def get_price_list(self, billing_territory):
		price_list = self.get_name_from_territory(billing_territory, "price_lists", "selling_price_list")
		return price_list and price_list[0] or None
		
	def get_tax_master(self, billing_territory):
		tax_master = self.get_name_from_territory(billing_territory, "sales_taxes_and_charges_masters", 
			"sales_taxes_and_charges_master")
		return tax_master and tax_master[0] or None
		
	def get_shipping_rules(self, shipping_territory):
		return self.get_name_from_territory(shipping_territory, "shipping_rules", "shipping_rule")
		
	def get_territory_ancestry(self, territory):
		from frappe.utils.nestedset import get_ancestors_of
		
		if not hasattr(self, "_territory_ancestry"):
			self._territory_ancestry = {}
			
		if not self._territory_ancestry.get(territory):
			self._territory_ancestry[territory] = get_ancestors_of("Territory", territory)

		return self._territory_ancestry[territory]
		
def validate_cart_settings(bean, method):
	frappe.bean("Shopping Cart Settings", "Shopping Cart Settings").run_method("validate")
