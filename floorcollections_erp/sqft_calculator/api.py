import frappe

from floorcollections_erp.sqft_calculator.calculator import calculate_sqft
from floorcollections_erp.sqft_calculator.sizes import TILE_SIZES


@frappe.whitelist()
def search_sizes(txt=None):
    txt = (txt or "").strip().lower()

    if not txt:
        return TILE_SIZES[:20]

    matches = [
        row
        for row in TILE_SIZES
        if txt in row["label"].lower()
    ]

    return matches[:20]


@frappe.whitelist()
def calculate(
    required_sqft,
    width,
    height,
    pieces_per_box=1,
    wastage_percent=0,
    sell_by="Box",
):
    return calculate_sqft(
        required_sqft=required_sqft,
        width=width,
        height=height,
        pieces_per_box=pieces_per_box,
        wastage_percent=wastage_percent,
        sell_by=sell_by,
    )
