# Copyright (c) 2026, Floor Collections and contributors
# For license information, please see license.txt

from statistics import mean

import frappe
from frappe import _
from frappe.utils import add_months, date_diff, flt, getdate, nowdate


def execute(filters=None):
    filters = frappe._dict(filters or {})
    validate_filters(filters)

    items = get_items(filters)
    sales_map = get_sales_history(filters)
    stock_map = get_stock_position(filters)

    analysis_months = get_analysis_months(
        filters.from_date,
        filters.to_date,
    )

    prepared_rows = []

    for item in items:
        sales = sales_map.get(item.name, [])
        stock = stock_map.get(item.name, frappe._dict())

        metrics = calculate_item_metrics(
            sales=sales,
            stock=stock,
            analysis_months=analysis_months,
            to_date=filters.to_date,
            ams_basis=filters.ams_basis,
        )

        prepared_rows.append(
            frappe._dict(
                {
                    "item_code": item.name,
                    "item_name": item.item_name,
                    "item_group": item.item_group,
                    "brand": item.brand,
                    **metrics,
                }
            )
        )

    apply_amc_tiers(prepared_rows)

    data = []

    for row in prepared_rows:
        row.dsls_score = get_dsls_score(row.dsls)
        row.isg_score = get_isg_score(
            row.dsls,
            row.inter_sale_gap,
            row.meaningful_sales,
        )
        row.months_active_score = get_months_active_score(
            row.months_active
        )

        row.demand_score = (
            row.dsls_score
            + row.isg_score
            + row.months_active_score
            + row.amc_score
        )

        row.demand_class = get_demand_class(row.demand_score)

        row.stock_risk = get_stock_risk(
            row.stock_cover,
            row.available_qty,
            row.average_monthly_sales,
        )

        row.recommendation = get_recommendation(row)

        if (
            filters.recommendation
            and row.recommendation != filters.recommendation
        ):
            continue

        data.append(row)

    data.sort(
        key=lambda row: (
            recommendation_priority(row.recommendation),
            -flt(row.stock_value),
        )
    )

    return (
        get_columns(),
        data,
        None,
        get_chart(data),
        get_report_summary(data),
    )


def validate_filters(filters):
    if not filters.company:
        filters.company = frappe.defaults.get_user_default("Company")

    if not filters.to_date:
        filters.to_date = nowdate()

    if not filters.from_date:
        filters.from_date = add_months(filters.to_date, -12)

    filters.from_date = getdate(filters.from_date)
    filters.to_date = getdate(filters.to_date)

    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date cannot be after To Date."))

    if not filters.ams_basis:
        filters.ams_basis = "Analysis Period"


def get_items(filters):
    conditions = [
        "item.disabled = 0",
        "item.is_sales_item = 1",
    ]
    values = {}

    if filters.item_group:
        conditions.append("item.item_group = %(item_group)s")
        values["item_group"] = filters.item_group

    if filters.brand:
        conditions.append("item.brand = %(brand)s")
        values["brand"] = filters.brand

    return frappe.db.sql(
        f"""
        SELECT
            item.name,
            item.item_name,
            item.item_group,
            item.brand
        FROM `tabItem` item
        WHERE {" AND ".join(conditions)}
        ORDER BY item.item_name
        """,
        values,
        as_dict=True,
    )


def get_sales_history(filters):
    conditions = [
        "si.docstatus = 1",
        "si.company = %(company)s",
        "si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
    ]

    values = {
        "company": filters.company,
        "from_date": filters.from_date,
        "to_date": filters.to_date,
    }

    if filters.warehouse:
        conditions.append("sii.warehouse = %(warehouse)s")
        values["warehouse"] = filters.warehouse

    rows = frappe.db.sql(
        f"""
        SELECT
            sii.item_code,
            si.posting_date,
            SUM(
                CASE
                    WHEN si.is_return = 1
                        THEN -ABS(sii.stock_qty)
                    ELSE ABS(sii.stock_qty)
                END
            ) AS net_qty
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si
            ON si.name = sii.parent
        WHERE {" AND ".join(conditions)}
        GROUP BY
            sii.item_code,
            si.posting_date
        ORDER BY
            sii.item_code,
            si.posting_date
        """,
        values,
        as_dict=True,
    )

    sales_map = {}

    for row in rows:
        sales_map.setdefault(row.item_code, []).append(row)

    return sales_map


def get_stock_position(filters):
    conditions = [
        "warehouse.company = %(company)s",
        "warehouse.is_group = 0",
    ]

    values = {
        "company": filters.company,
    }

    if filters.warehouse:
        conditions.append("bin.warehouse = %(warehouse)s")
        values["warehouse"] = filters.warehouse

    rows = frappe.db.sql(
        f"""
        SELECT
            bin.item_code,
            SUM(bin.actual_qty) AS available_qty,
            SUM(bin.actual_qty * bin.valuation_rate) AS stock_value
        FROM `tabBin` bin
        INNER JOIN `tabWarehouse` warehouse
            ON warehouse.name = bin.warehouse
        WHERE {" AND ".join(conditions)}
        GROUP BY bin.item_code
        """,
        values,
        as_dict=True,
    )

    return {
        row.item_code: row
        for row in rows
    }


def calculate_item_metrics(
    sales,
    stock,
    analysis_months,
    to_date,
    ams_basis,
):
    positive_sales = [
        row for row in sales
        if flt(row.net_qty) > 0
    ]

    positive_sale_dates = sorted(
        {
            getdate(row.posting_date)
            for row in positive_sales
        }
    )

    meaningful_sales = len(positive_sale_dates)

    last_sale_date = (
        positive_sale_dates[-1]
        if positive_sale_dates
        else None
    )

    dsls = (
        date_diff(to_date, last_sale_date)
        if last_sale_date
        else None
    )

    inter_sale_gap = calculate_inter_sale_gap(
        positive_sale_dates
    )

    active_months = len(
        {
            (
                getdate(row.posting_date).year,
                getdate(row.posting_date).month,
            )
            for row in positive_sales
        }
    )

    total_sales_qty = sum(
        flt(row.net_qty)
        for row in sales
    )

    denominator = analysis_months

    if ams_basis == "Active Months":
        denominator = max(active_months, 1)

    average_monthly_sales = (
        max(total_sales_qty, 0) / max(denominator, 1)
    )

    available_qty = flt(stock.get("available_qty"))
    stock_value = flt(stock.get("stock_value"))

    stock_cover = None

    if average_monthly_sales > 0:
        stock_cover = (
            available_qty / average_monthly_sales
        )

    return {
        "last_sale_date": last_sale_date,
        "dsls": dsls,
        "meaningful_sales": meaningful_sales,
        "inter_sale_gap": inter_sale_gap,
        "months_active": active_months,
        "total_sales_qty": total_sales_qty,
        "average_monthly_sales": average_monthly_sales,
        "available_qty": available_qty,
        "stock_value": stock_value,
        "stock_cover": stock_cover,
    }


def calculate_inter_sale_gap(sale_dates):
    if len(sale_dates) < 5:
        return None

    gaps = [
        date_diff(sale_dates[index], sale_dates[index - 1])
        for index in range(1, len(sale_dates))
    ]

    return mean(gaps) if gaps else None


def apply_amc_tiers(rows):
    moving_rows = sorted(
        [
            row for row in rows
            if flt(row.average_monthly_sales) > 0
        ],
        key=lambda row: row.average_monthly_sales,
        reverse=True,
    )

    total = len(moving_rows)

    for row in rows:
        row.amc_tier = "Danger"
        row.amc_score = 0

    if not total:
        return

    for index, row in enumerate(moving_rows):
        percentile_position = (index + 1) / total

        if percentile_position <= 0.25:
            row.amc_tier = "Top 25%"
            row.amc_score = 3

        elif percentile_position <= 0.75:
            row.amc_tier = "Middle"
            row.amc_score = 2

        else:
            row.amc_tier = "Low"
            row.amc_score = 1


def get_dsls_score(dsls):
    if dsls is None:
        return 0

    if dsls <= 30:
        return 3

    if dsls <= 60:
        return 2

    if dsls <= 120:
        return 1

    return 0


def get_isg_score(dsls, inter_sale_gap, meaningful_sales):
    if (
        meaningful_sales < 5
        or dsls is None
        or not inter_sale_gap
    ):
        return 0

    if dsls <= 1.5 * inter_sale_gap:
        return 2

    if dsls <= 2.5 * inter_sale_gap:
        return 1

    return 0


def get_months_active_score(months_active):
    if months_active >= 9:
        return 3

    if months_active >= 5:
        return 2

    if months_active >= 2:
        return 1

    return 0


def get_demand_class(score):
    if score >= 9:
        return "Strong"

    if score >= 6:
        return "Moderate"

    if score >= 3:
        return "Weak"

    return "Dormant"


def get_stock_risk(stock_cover, available_qty, ams):
    if available_qty <= 0:
        return "No Stock"

    if ams <= 0 or stock_cover is None:
        return "Dead / No Demand"

    if stock_cover < 1:
        return "Stock-out Risk"

    if stock_cover < 3:
        return "Healthy"

    if stock_cover < 6:
        return "Overstock Risk"

    return "Capital Trapped"


def get_recommendation(row):
    if row.available_qty <= 0:
        if row.average_monthly_sales > 0:
            return "Urgent Purchase"

        return "Monitor"

    if row.average_monthly_sales <= 0:
        return "Stop Purchase"

    if row.stock_cover is None:
        return "Manual Review"

    if row.stock_cover < 1:
        if row.demand_score >= 6:
            return "Urgent Purchase"

        return "Purchase Soon"

    if row.stock_cover < 3:
        return "Maintain"

    if row.stock_cover < 6:
        return "Reduce Purchase"

    return "Stop Purchase"


def recommendation_priority(recommendation):
    priority = {
        "Urgent Purchase": 1,
        "Purchase Soon": 2,
        "Manual Review": 3,
        "Maintain": 4,
        "Monitor": 5,
        "Reduce Purchase": 6,
        "Stop Purchase": 7,
    }

    return priority.get(recommendation, 99)


def get_analysis_months(from_date, to_date):
    return max(
        1,
        (
            (to_date.year - from_date.year) * 12
            + to_date.month
            - from_date.month
            + 1
        ),
    )


def get_columns():
    return [
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 190,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": _("Item Group"),
            "fieldname": "item_group",
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 150,
        },
        {
            "label": _("Brand"),
            "fieldname": "brand",
            "fieldtype": "Link",
            "options": "Brand",
            "width": 120,
        },
        {
            "label": _("Last Sale"),
            "fieldname": "last_sale_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("DSLS"),
            "fieldname": "dsls",
            "fieldtype": "Int",
            "width": 75,
        },
        {
            "label": _("DSLS Score"),
            "fieldname": "dsls_score",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("Meaningful Sales"),
            "fieldname": "meaningful_sales",
            "fieldtype": "Int",
            "width": 110,
        },
        {
            "label": _("ISG Days"),
            "fieldname": "inter_sale_gap",
            "fieldtype": "Float",
            "precision": 1,
            "width": 90,
        },
        {
            "label": _("ISG Score"),
            "fieldname": "isg_score",
            "fieldtype": "Int",
            "width": 85,
        },
        {
            "label": _("Months Active"),
            "fieldname": "months_active",
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "label": _("AMS"),
            "fieldname": "average_monthly_sales",
            "fieldtype": "Float",
            "precision": 2,
            "width": 100,
        },
        {
            "label": _("AMC Tier"),
            "fieldname": "amc_tier",
            "fieldtype": "Data",
            "width": 95,
        },
        {
            "label": _("Demand Score"),
            "fieldname": "demand_score",
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "label": _("Demand Class"),
            "fieldname": "demand_class",
            "fieldtype": "Data",
            "width": 105,
        },
        {
            "label": _("Available Qty"),
            "fieldname": "available_qty",
            "fieldtype": "Float",
            "precision": 2,
            "width": 105,
        },
        {
            "label": _("Stock Cover"),
            "fieldname": "stock_cover",
            "fieldtype": "Float",
            "precision": 2,
            "width": 100,
        },
        {
            "label": _("Stock Value"),
            "fieldname": "stock_value",
            "fieldtype": "Currency",
            "width": 125,
        },
        {
            "label": _("Stock Risk"),
            "fieldname": "stock_risk",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": _("Recommendation"),
            "fieldname": "recommendation",
            "fieldtype": "Data",
            "width": 145,
        },
    ]


def get_report_summary(data):
    urgent_items = sum(
        1 for row in data
        if row.recommendation == "Urgent Purchase"
    )

    stop_purchase_items = sum(
        1 for row in data
        if row.recommendation == "Stop Purchase"
    )

    capital_trapped_value = sum(
        flt(row.stock_value)
        for row in data
        if row.stock_risk == "Capital Trapped"
    )

    total_stock_value = sum(
        flt(row.stock_value)
        for row in data
    )

    return [
        {
            "label": _("Urgent Purchase Items"),
            "value": urgent_items,
            "indicator": "red",
            "datatype": "Int",
        },
        {
            "label": _("Stop Purchase Items"),
            "value": stop_purchase_items,
            "indicator": "orange",
            "datatype": "Int",
        },
        {
            "label": _("Capital Trapped Value"),
            "value": capital_trapped_value,
            "indicator": "red",
            "datatype": "Currency",
        },
        {
            "label": _("Total Stock Value"),
            "value": total_stock_value,
            "indicator": "blue",
            "datatype": "Currency",
        },
    ]


def get_chart(data):
    categories = [
        "Urgent Purchase",
        "Purchase Soon",
        "Maintain",
        "Monitor",
        "Reduce Purchase",
        "Stop Purchase",
        "Manual Review",
    ]

    counts = [
        sum(
            1 for row in data
            if row.recommendation == category
        )
        for category in categories
    ]

    return {
        "data": {
            "labels": categories,
            "datasets": [
                {
                    "name": _("Items"),
                    "values": counts,
                }
            ],
        },
        "type": "bar",
        "height": 280,
    }
