import math


MM2_PER_SQFT = 92903.04


def calculate_sqft(
    required_sqft,
    width,
    height,
    pieces_per_box=1,
    wastage_percent=0,
    sell_by="Box",
):
    required_sqft = float(required_sqft or 0)
    width = float(width or 0)
    height = float(height or 0)
    pieces_per_box = int(pieces_per_box or 1)
    wastage_percent = float(wastage_percent or 0)

    if required_sqft <= 0:
        raise ValueError("Required sqft must be greater than 0")

    if width <= 0 or height <= 0:
        raise ValueError("Width and height must be greater than 0")

    if pieces_per_box <= 0:
        raise ValueError("Pieces per box must be greater than 0")

    sqft_per_piece = (width * height) / MM2_PER_SQFT
    sqft_per_box = sqft_per_piece * pieces_per_box

    required_with_wastage = (
        required_sqft * (1 + wastage_percent / 100)
    )

    sell_by = (sell_by or "Box").strip().lower()

    if sell_by == "piece":
        pieces_required = math.ceil(
            required_with_wastage / sqft_per_piece
        )

        boxes_required = math.ceil(
            pieces_required / pieces_per_box
        )

        actual_pieces = pieces_required

    else:
        boxes_required = math.ceil(
            required_with_wastage / sqft_per_box
        )

        pieces_required = (
            boxes_required * pieces_per_box
        )

        actual_pieces = pieces_required

    actual_coverage = (
        actual_pieces * sqft_per_piece
    )

    extra_coverage = (
        actual_coverage - required_with_wastage
    )

    return {
        "required_sqft": round(required_sqft, 2),
        "required_with_wastage": round(required_with_wastage, 2),
        "width": width,
        "height": height,
        "pieces_per_box": pieces_per_box,
        "sqft_per_piece": round(sqft_per_piece, 4),
        "sqft_per_box": round(sqft_per_box, 4),
        "boxes_required": boxes_required,
        "pieces_required": pieces_required,
        "actual_coverage": round(actual_coverage, 2),
        "extra_coverage": round(extra_coverage, 2),
        "wastage_percent": wastage_percent,
        "sell_by": "Piece" if sell_by == "piece" else "Box",
    }
