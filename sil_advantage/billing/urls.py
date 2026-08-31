"""Billing URLs."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from sil_advantage.billing import views

router = SimpleRouter()
router.register("clinical_orders", views.ClinicalOrderViewSet)
router.register("invoices", views.InvoiceViewSet)
router.register("billable_items", views.BillableItemViewSet)
router.register("payments", views.PaymentViewSet)
router.register("refunds", views.RefundViewSet)
router.register("refund_lines", views.RefundLineViewSet)

urlpatterns = router.urls
urlpatterns += (
    path(
        "wallets/",
        views.WalletsView.as_view(),
        name="wallets",
    ),
    path(
        "clinical_orders/<uuid:id>/transition/<slug:workflow_state>/",
        views.ClinicalOrderTransitionView.as_view(),
        name="clinical-order-transition",
    ),
    path(
        "invoices/<uuid:id>/transition/<slug:workflow_state>/",
        views.InvoiceTransitionView.as_view(),
        name="invoice-transition",
    ),
    path(
        "refunds/<uuid:id>/transition/<slug:workflow_state>/",
        views.RefundTransitionView.as_view(),
        name="refund-transition",
    ),
)
