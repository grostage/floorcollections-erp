import frappe
from frappe.utils import today, add_days


def sales_order_after_insert(doc, method=None):
    """
    Direct Sales Order flow:
    - Detect the Lead linked to the selected Customer
    - Create Opportunity
    - Create Quotation
    - Link everything back to the Sales Order
    """

    if frappe.flags.in_direct_so_flow:
        return

    if doc.docstatus != 0:
        return

    if not doc.customer:
        return

    if sales_order_has_quotation_reference(doc):
        return

    if doc.get("custom_direct_so_flow_created"):
        return

    frappe.flags.in_direct_so_flow = True

    try:
        lead_name = frappe.db.get_value(
            "Customer",
            doc.customer,
            "lead_name",
        )

        if lead_name and doc.meta.has_field("custom_source_lead"):
            frappe.db.set_value(
                "Sales Order",
                doc.name,
                "custom_source_lead",
                lead_name,
                update_modified=False,
            )
            doc.custom_source_lead = lead_name

        opportunity = create_opportunity_from_sales_order(doc)
        quotation = create_quotation_from_sales_order(doc, opportunity)

        link_sales_order_to_quotation(doc, quotation)

        frappe.db.set_value(
            "Sales Order",
            doc.name,
            {
                "custom_direct_so_flow_created": 1,
                "custom_auto_opportunity": opportunity.name,
                "custom_auto_quotation": quotation.name,
            },
        )

        doc.add_comment(
            "Info",
            f"Direct SO flow created Opportunity <b>{opportunity.name}</b> "
            f"and Quotation <b>{quotation.name}</b>.",
        )

    finally:
        frappe.flags.in_direct_so_flow = False

def sales_order_on_submit(doc, method=None):
    """
    Finalize the automatically created sales chain when the Sales Order
    is submitted.
    """

    if frappe.flags.in_direct_so_flow:
        return

    if not doc.get("custom_direct_so_flow_created"):
        return

    frappe.flags.in_direct_so_flow = True

    try:
        quotation_name = doc.get("custom_auto_quotation")
        opportunity_name = doc.get("custom_auto_opportunity")

        if quotation_name and frappe.db.exists("Quotation", quotation_name):
            quotation = frappe.get_doc("Quotation", quotation_name)

            # A submitted Quotation is required for normal ERPNext status flow.
            if quotation.docstatus == 0:
                quotation.flags.ignore_permissions = True
                quotation.submit()

            # Ensure every Sales Order Item points to its Quotation Item.
            link_sales_order_to_quotation(doc, quotation)

            # Recalculate the Quotation's ordered quantity/status.
            quotation.reload()
            quotation.set_status(update=True)

        if opportunity_name and frappe.db.exists("Opportunity", opportunity_name):
            opportunity = frappe.get_doc("Opportunity", opportunity_name)

            if opportunity.docstatus == 0:
                opportunity.db_set("status", "Converted", update_modified=True)

        doc.add_comment(
            "Info",
            "Auto-created Quotation and Opportunity were finalized after Sales Order submission.",
        )

    finally:
        frappe.flags.in_direct_so_flow = False

def sales_order_on_update(doc, method=None):
    """
    Sync draft Sales Order changes back to the auto-created
    Opportunity and Quotation.
    """

    if frappe.flags.in_direct_so_flow:
        return

    if doc.docstatus != 0:
        return

    if not doc.get("custom_direct_so_flow_created"):
        return

    frappe.flags.in_direct_so_flow = True

    try:
        opportunity_name = doc.get("custom_auto_opportunity")
        quotation_name = doc.get("custom_auto_quotation")

        if opportunity_name and frappe.db.exists(
            "Opportunity",
            opportunity_name,
        ):
            sync_opportunity_from_sales_order(
                doc,
                opportunity_name,
            )

        if quotation_name and frappe.db.exists(
            "Quotation",
            quotation_name,
        ):
            sync_quotation_from_sales_order(
                doc,
                quotation_name,
            )

            quotation = frappe.get_doc(
                "Quotation",
                quotation_name,
            )

            link_sales_order_to_quotation(
                doc,
                quotation,
            )

    finally:
        frappe.flags.in_direct_so_flow = False


def sales_order_has_quotation_reference(doc):
    for item in doc.get("items", []):
        if item.get("prevdoc_docname") or item.get("quotation_item"):
            return True
    return False


def create_opportunity_from_sales_order(doc):
    opportunity = frappe.new_doc("Opportunity")
    opportunity.opportunity_from = "Customer"
    opportunity.party_name = doc.customer
    opportunity.customer_name = doc.customer_name
    opportunity.opportunity_type = "Sales"
    opportunity.status = "Open"
    opportunity.transaction_date = doc.transaction_date or today()
    opportunity.company = doc.company
    opportunity.title = doc.customer_name or doc.customer

    if doc.get("custom_source_lead"):
    	if opportunity.meta.has_field("custom_source_lead"):
        	opportunity.custom_source_lead = doc.custom_source_lead

    if opportunity.meta.has_field("custom_source_sales_order"):
        opportunity.custom_source_sales_order = doc.name

    copy_common_fields(doc, opportunity)

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
    quotation.valid_till = (
        doc.get("delivery_date")
        or add_days(today(), 30)
    )

    copy_price_fields(doc, quotation)
    copy_common_fields(doc, quotation)

    if doc.get("custom_source_lead"):
        if quotation.meta.has_field("custom_source_lead"):
            quotation.custom_source_lead = doc.custom_source_lead

    if has_field("Quotation", "opportunity"):
        quotation.opportunity = opportunity.name

    if has_field("Quotation", "custom_source_sales_order"):
        quotation.custom_source_sales_order = doc.name

    append_items_to_quotation(doc, quotation)
    append_taxes_to_quotation(doc, quotation)

    quotation.insert(ignore_permissions=True)
    return quotation


def sync_opportunity_from_sales_order(doc, opportunity_name):
    opportunity = frappe.get_doc("Opportunity", opportunity_name)

    if opportunity.docstatus != 0:
        return

    opportunity.party_name = doc.customer
    opportunity.customer_name = doc.customer_name
    opportunity.transaction_date = doc.transaction_date or today()
    opportunity.company = doc.company
    opportunity.title = doc.customer_name or doc.customer

    copy_common_fields(doc, opportunity)

    opportunity.set("items", [])
    for item in doc.get("items", []):
        opportunity.append("items", {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "description": item.description,
            "qty": item.qty,
            "uom": item.uom,
            "rate": item.rate or 0
        })

    opportunity.save(ignore_permissions=True)


def sync_quotation_from_sales_order(doc, quotation_name):
    quotation = frappe.get_doc("Quotation", quotation_name)

    if quotation.docstatus != 0:
        return

    quotation.party_name = doc.customer
    quotation.customer_name = doc.customer_name
    quotation.company = doc.company
    quotation.transaction_date = doc.transaction_date or today()
    quotation.valid_till = doc.get("delivery_date") or quotation.valid_till or add_days(today(), 30)

    copy_price_fields(doc, quotation)
    copy_common_fields(doc, quotation)

    quotation.set("items", [])
    quotation.set("taxes", [])

    append_items_to_quotation(doc, quotation)
    append_taxes_to_quotation(doc, quotation)

    quotation.save(ignore_permissions=True)


def append_items_to_quotation(doc, quotation):
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


def append_taxes_to_quotation(doc, quotation):
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


def link_sales_order_to_quotation(doc, quotation):
    """
    This is important for ERPNext connection/status behaviour.
    It links Sales Order Items back to Quotation Items.
    """

    so_items = doc.get("items", [])
    quotation_items = quotation.get("items", [])

    for index, so_item in enumerate(so_items):
        if index >= len(quotation_items):
            continue

        q_item = quotation_items[index]
        values = {}

        if has_field("Sales Order Item", "prevdoc_docname"):
            values["prevdoc_docname"] = quotation.name

        if has_field("Sales Order Item", "quotation_item"):
            values["quotation_item"] = q_item.name

        if values:
            frappe.db.set_value("Sales Order Item", so_item.name, values)

    frappe.db.commit()


def copy_price_fields(source, target):
    price_fields = [
        "currency",
        "selling_price_list",
        "price_list_currency",
        "plc_conversion_rate",
        "conversion_rate",
        "ignore_pricing_rule",
        "apply_discount_on",
        "additional_discount_percentage",
        "discount_amount",
    ]

    for field in price_fields:
        if has_field(target.doctype, field) and source.get(field) is not None:
            target.set(field, source.get(field))


def copy_common_fields(source, target):
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
        if has_field(target.doctype, field) and source.get(field):
            target.set(field, source.get(field))


def has_field(doctype, fieldname):
    return frappe.get_meta(doctype).has_field(fieldname)

