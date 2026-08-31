"""Billing scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

# Orders

ORDER_READ = SCOPE_NODE(
    "advantage.order.read",
    "View orders",
)
ORDER_WRITE = SCOPE_NODE(
    "advantage.order.write",
    "Edit orders",
)


# Invoices

INVOICE_READ = SCOPE_NODE(
    "advantage.invoice.read",
    "View invoices",
)
INVOICE_WRITE = SCOPE_NODE(
    "advantage.invoice.write",
    "Edit invoices",
)


# Billed Items

BILLED_ITEM_READ = SCOPE_NODE(
    "advantage.billed_item.read",
    "View billed items",
)
BILLED_ITEM_WRITE = SCOPE_NODE(
    "advantage.billed_item.write",
    "Edit billed items",
)

# Refunds

REFUND_READ = SCOPE_NODE(
    "advantage.refund.read",
    "View refunds",
)
REFUND_WRITE = SCOPE_NODE(
    "advantage.refund.write",
    "Edit refunds",
)

# Refunded LInes

REFUND_LINE_READ = SCOPE_NODE(
    "advantage.refund_line.read",
    "View refunded lines",
)
REFUND_LINE_WRITE = SCOPE_NODE(
    "advantage.refund_line.write",
    "Edit refunded lines",
)
