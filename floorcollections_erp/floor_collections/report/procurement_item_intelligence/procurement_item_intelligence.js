// Copyright (c) 2026, Floor Collections and contributors
// For license information, please see license.txt

frappe.query_reports["Procurement Item Intelligence"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(
                frappe.datetime.get_today(),
                -12
            ),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse",
            get_query() {
                return {
                    filters: {
                        company:
                            frappe.query_report.get_filter_value("company"),
                        is_group: 0,
                    },
                };
            },
        },
        {
            fieldname: "item_group",
            label: __("Item Group"),
            fieldtype: "Link",
            options: "Item Group",
        },
        {
            fieldname: "brand",
            label: __("Brand"),
            fieldtype: "Link",
            options: "Brand",
        },
        {
            fieldname: "ams_basis",
            label: __("AMS Basis"),
            fieldtype: "Select",
            options: [
                "Analysis Period",
                "Active Months",
            ],
            default: "Analysis Period",
        },
        {
            fieldname: "recommendation",
            label: __("Recommendation"),
            fieldtype: "Select",
            options: [
                "",
                "Urgent Purchase",
                "Purchase Soon",
                "Maintain",
                "Monitor",
                "Reduce Purchase",
                "Stop Purchase",
                "Manual Review",
            ],
        },
    ],
};
