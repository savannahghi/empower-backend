"""Billing filters."""
import django_filters

from sil_advantage.billing.models import (
    BillableItem,
    ClinicalOrder,
    Invoice,
    Payment,
    Refund,
    RefundLine,
)
from sil_advantage.common.filters.base import CommonFieldsFilterset, ListFilter


class ClinicalOrderFilter(CommonFieldsFilterset):
    """ClinicalOrder filter."""

    workflow_state = ListFilter()

    class Meta:
        """Filter options."""

        model = ClinicalOrder
        fields = "__all__"


class InvoiceFilter(CommonFieldsFilterset):
    """Invoice filter."""

    workflow_state = ListFilter()

    class Meta:
        """Filter options."""

        model = Invoice
        fields = "__all__"


class PaymentFilter(CommonFieldsFilterset):
    """Payment filter."""

    workflow_state = ListFilter()

    class Meta:
        """Filter options."""

        model = Payment
        fields = "__all__"


class BillableItemFilter(CommonFieldsFilterset):
    """BillableItem filter."""

    class Meta:
        """Filter options."""

        model = BillableItem
        fields = "__all__"


class RefundFilter(CommonFieldsFilterset):
    """Refund filter."""

    workflow_state = ListFilter()
    sales_invoice_id = django_filters.CharFilter(
        field_name="invoice__sales_invoice_id", lookup_expr="iexact"
    )

    class Meta:
        """Filter options."""

        model = Refund
        fields = "__all__"


class RefundLineFilter(CommonFieldsFilterset):
    """RefundLine filter."""

    class Meta:
        """Filter options."""

        model = RefundLine
        fields = "__all__"
