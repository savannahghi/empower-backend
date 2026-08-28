"""Segments URLs."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from sil_advantage.segments import views

router = SimpleRouter()
router.register("segment", views.SegmentViewSet)
router.register("segment-message", views.SegmentMessageViewSet)
router.register("segment-member", views.SegmentMemberViewSet)
router.register(
    "segment-member-transition-log", views.SegmentMemberTransitionLogViewSet
)
router.register("segment-message-delivery", views.SegmentMessageDeliveryViewSet)
router.register("segment-upload", views.SegmentUploadViewSet)
router.register("segment-transition-log", views.SegmentTransitionLogViewSet)
router.register("template", views.MessageTemplateViewSet)
router.register("template-transition-log", views.MessageTemplateTransitionLogViewSet)
router.register("filters", views.FilterViewSet)
router.register("filter-groups", views.FilterGroupViewSet)
router.register("filter-group-filters", views.FilterGroupFilterViewSet)
router.register("journey", views.JourneyViewSet)
router.register("journey-member", views.JourneyMemberViewSet)
router.register("journey-segment", views.JourneySegmentViewSet)
router.register("journey-attributes", views.JourneyAttributesViewSet)

urlpatterns = router.urls

urlpatterns += (
    path(
        "segment/<uuid:id>/transition/<slug:status>/",
        views.SegmentTransitionLogView.as_view(),
        name="segment-transition",
    ),
    path(
        "template/<uuid:id>/transition/<slug:status>/",
        views.MessageTemplateTransitionLogView.as_view(),
        name="message-transition",
    ),
    path(
        "segment-member/<uuid:id>/transition/<slug:status>/",
        views.SegmentMemberTransitionLogView.as_view(),
        name="segment-member-transition",
    ),
    path(
        "segment/<uuid:segment_id>/update-filters/",
        views.UpdateSegmentFiltersView.as_view(),
        name="update-segment-filters",
    ),
)
