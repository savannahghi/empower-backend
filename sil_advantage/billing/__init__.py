"""Thin wrapper around ERP invoicing/billing."""

BILLING_CLASSES = [
    ("CASH", "Cash"),
    ("CREDIT", "Credit"),
]
REFUND_REASONS = [
    ("01", "Missing Quantity"),
    ("02", "Missing Item"),
    ("03", "Damaged"),
    ("04", "Wasted"),
    ("05", "Raw Material Shortage"),
    ("06", "Refund"),
    ("07", "Wrong Customer PIN"),
    ("08", "Wrong Customer name"),
    ("09", "Wrong Amount/price"),
    ("10", "Wrong Quantity"),
    ("11", "Wrong Item(s)"),
    ("12", "Wrong tax type"),
    ("13", "Other reason"),
]
NOT_REFUNDED = "NOT_REFUNDED"
PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
FULLY_REFUNDED = "FULLY_REFUNDED"

REFUND_STATUS = [
    (NOT_REFUNDED, "Not Refunded"),
    (PARTIALLY_REFUNDED, "Partially Refunded"),
    (FULLY_REFUNDED, "Fully Refunded"),
]
