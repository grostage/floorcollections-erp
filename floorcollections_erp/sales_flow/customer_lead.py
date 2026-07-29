import frappe


def customer_after_insert(doc, method=None):
    """
    Create and link a Lead when a new Customer is created with
    custom_create_lead enabled.
    """

    if not doc.get("custom_create_lead"):
        return

    # Customer already linked to a Lead
    if doc.get("lead_name"):
        return

    lead_name = find_existing_lead(doc)

    if not lead_name:
        lead_name = create_lead_from_customer(doc)

    # Standard ERPNext Customer → Lead link
    if doc.meta.has_field("lead_name"):
        frappe.db.set_value(
            "Customer",
            doc.name,
            "lead_name",
            lead_name,
            update_modified=False,
        )

    frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": "Customer",
            "reference_name": doc.name,
            "content": f"Lead <b>{lead_name}</b> created and linked automatically.",
        }
    ).insert(ignore_permissions=True)


def find_existing_lead(customer):
    mobile_no = customer.get("mobile_no")

    if mobile_no:
        existing = frappe.db.get_value(
            "Lead",
            {"mobile_no": mobile_no},
            "name",
        )

        if existing:
            return existing

    return None


def create_lead_from_customer(customer):
    lead = frappe.new_doc("Lead")

    lead.lead_name = customer.customer_name
    lead.company_name = (
        customer.customer_name
        if customer.customer_type == "Company"
        else None
    )

    if lead.meta.has_field("mobile_no"):
        lead.mobile_no = customer.get("mobile_no")

    if lead.meta.has_field("status"):
        lead.status = "Lead"

    if lead.meta.has_field("source") and customer.get("custom_lead_source"):
        lead.source = customer.custom_lead_source

    copy_custom_fields(customer, lead)

    lead.flags.ignore_permissions = True
    lead.insert()

    return lead.name


def copy_custom_fields(customer, lead):
    fields = [
        "custom_need_stage",
        "custom_product_range",
        "custom_decision_maker",
        "custom_expected_closing",
        "custom_construction_type",
        "custom_new_or_renovation",
        "custom_build_area",
    ]

    for fieldname in fields:
        value = customer.get(fieldname)

        if (
            value not in (None, "")
            and lead.meta.has_field(fieldname)
        ):
            lead.set(fieldname, value)
