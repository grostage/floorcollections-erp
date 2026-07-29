import frappe
from frappe.utils import today, add_days


def sales_order_after_insert(doc, method=None):
    """
    Auto-create Opportunity and Quotation when Sales Order is created directly.
    Runs once only.
    """

    if doc.get("custom_auto_created_opportunity"):
        return

    if doc.get("custom_opportunity") or doc.get("custom_quotation"):
        return

    if not doc.customer:
        return

    lead_name = None

    if doc.get("custom_is_new_customer_from_so"):
        lead_name = create_lead_from_sales_order(doc)

    opportunity = create_opportunity_from_sales_order(doc, lead_name)
    quotation = create_quotation_from_sales_order(doc, opportunity)

    frappe.db.set_value("Sales Order", doc.name, {
        "custom_lead": lead_name,
        "custom_opportunity": opportunity.name,
        "custom_quotation": quotation.name,
        "custom_auto_created_opportunity": 1
    })

    doc.add_comment(
        "Info",
        "Auto-created Opportunity <b>{0}</b> and Quotation <b>{1}</b>.".format(
            opportunity.name,
            quotation.name
        )
    )


def create_lead_from_sales_order(doc):
    customer_name = frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer
    mobile_no = frappe.db.get_value("Customer", doc.customer, "mobile_no")

    existing_lead = None

    if mobile_no:
        existing_lead = frappe.db.get_value("Lead", {"mobile_no": mobile_no}, "name")

    if existing_lead:
        return existing_lead

    lead = frappe.new_doc("Lead")
    lead.lead_name = customer_name
    lead.company_name = customer_name
    lead.mobile_no = mobile_no
    lead.status = "Lead"

    if doc.get("source"):
        lead.source = doc.get("source")

    copy_common_custom_fields(doc, lead)

    lead.insert(ignore_permissions=True)
    return lead.name


def create_opportunity_from_sales_order(doc, lead_name=None):
    opportunity = frappe.new_doc("Opportunity")
    opportunity.opportunity_from = "Customer"
    opportunity.party_name = doc.customer
    opportunity.customer_name = doc.customer_name
    opportunity.opportunity_type = "Sales"
    opportunity.status = "Open"
    opportunity.transaction_date = doc.transaction_date or today()
    opportunity.company = doc.company
    opportunity.title = doc.customer_name or doc.customer

    copy_common_custom_fields(doc, opportunity)

    if lead_name and has_field("Opportunity", "custom_lead"):
        opportunity.custom_lead = lead_name

    for item in doc.get("items", []):
        opportunity.append("items", {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "description": item.description,
            "qty": item.qty,
            "uom": item.uom,
            "rate": item.rate or 0
        })

    opportunity.insert(ignore_permissions=True)
    return opportunity


def create_quotation_from_sales_order(doc, opportunity):
    quotation = frappe.new_doc("Quotation")
    quotation.quotation_to = "Customer"
    quotation.party_name = doc.customer
    quotation.customer_name = doc.customer_name
    quotation.company = doc.company
    quotation.transaction_date = doc.transaction_date or today()
    quotation.valid_till = doc.get("delivery_date") or add_days(today(), 30)

    quotation.currency = doc.currency
    quotation.selling_price_list = doc.selling_price_list
    quotation.price_list_currency = doc.price_list_currency
    quotation.plc_conversion_rate = doc.plc_conversion_rate
    quotation.conversion_rate = doc.conversion_rate

    copy_common_custom_fields(doc, quotation)

    if has_field("Quotation", "custom_opportunity"):
        quotation.custom_opportunity = opportunity.name

    for item in doc.get("items", []):
        quotation.append("items", {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "description": item.description,
            "qty": item.qty,
            "uom": item.uom,
            "stock_uom": item.stock_uom,
            "conversion_factor": item.conversion_factor,
            "rate": item.rate,
            "amount": item.amount,
            "warehouse": item.warehouse
        })

    for tax in doc.get("taxes", []):
        quotation.append("taxes", {
            "charge_type": tax.charge_type,
            "account_head": tax.account_head,
            "description": tax.description,
            "rate": tax.rate,
            "tax_amount": tax.tax_amount,
            "total": tax.total,
            "cost_center": tax.cost_center
        })

    quotation.insert(ignore_permissions=True)
    return quotation


def copy_common_custom_fields(source_doc, target_doc):
    fields = [
        "custom_need_stage",
        "custom_product_range",
        "custom_decision_maker",
        "custom_other_decision_maker",
        "custom_expected_closing",
        "source",
        "custom_referred_by_customer",
        "custom_referred_by_b2b",
        "custom_other_referrer_name",
        "custom_construction_type",
        "custom_new_or_renovation",
        "custom_build_area",
        "custom_value_of_selection",
        "custom_referred_by_employee",
        "custom_marketing_type",
        "custom_digital_platform",
        "custom_other_platform",
    ]

    for field in fields:
        if has_field(target_doc.doctype, field) and source_doc.get(field):
            target_doc.set(field, source_doc.get(field))


def has_field(doctype, fieldname):
    return frappe.db.exists("Custom Field", {
        "dt": doctype,
        "fieldname": fieldname
    }) or frappe.get_meta(doctype).has_field(fieldname)
