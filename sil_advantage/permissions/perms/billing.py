"""Billing permissions."""
from sil_auth_backends.utilities.utilities import PERM_NODE

# Clinical Orders

ORDER_VIEW = PERM_NODE(
    "advantage.order_list",
    "View orders",
)

ORDER_CREATE = PERM_NODE(
    "advantage.order_create",
    "Create orders",
)

ORDER_EDIT = PERM_NODE(
    "advantage.order_edit",
    "Edit orders",
)

ORDER_DELETE = PERM_NODE(
    "advantage.order_delete",
    "Remove orders",
)


# Invoices

INVOICE_VIEW = PERM_NODE(
    "advantage.invoice_list",
    "View invoices",
)

INVOICE_CREATE = PERM_NODE(
    "advantage.invoice_create",
    "Create invoices",
)

INVOICE_EDIT = PERM_NODE(
    "advantage.invoice_edit",
    "Edit invoices",
)

INVOICE_DELETE = PERM_NODE(
    "advantage.invoice_delete",
    "Remove invoices",
)


# Billed Items

BILLED_ITEM_VIEW = PERM_NODE(
    "advantage.billed_item_list",
    "View billed items",
)

BILLED_ITEM_CREATE = PERM_NODE(
    "advantage.billed_item_create",
    "Create billed items",
)

BILLED_ITEM_EDIT = PERM_NODE(
    "advantage.billed_item_edit",
    "Edit billed items",
)

BILLED_ITEM_DELETE = PERM_NODE(
    "advantage.billed_item_delete",
    "Remove billed items",
)

BILLED_ITEM_OVERRIDE_PRICE = PERM_NODE(
    "advantage.billed_item_override_price",
    "Override prices when billing",
)


# Refunds

REFUND_VIEW = PERM_NODE(
    "advantage.refund_list",
    "View refunds",
)

REFUND_CREATE = PERM_NODE(
    "advantage.refund_create",
    "Create refunds",
)

REFUND_EDIT = PERM_NODE(
    "advantage.refund_edit",
    "Edit refunds",
)

REFUND_DELETE = PERM_NODE(
    "advantage.refund_delete",
    "Remove refunds",
)

# Refunded Lines

REFUND_LINE_VIEW = PERM_NODE(
    "advantage.refund_line_list",
    "View refunded lines",
)

REFUND_LINE_CREATE = PERM_NODE(
    "advantage.refund_line_create",
    "Create refunded lines",
)

REFUND_LINE_EDIT = PERM_NODE(
    "advantage.refund_line_edit",
    "Edit refunded lines",
)

REFUND_LINE_DELETE = PERM_NODE(
    "advantage.refund_line_delete",
    "Remove refunded lines",
)
