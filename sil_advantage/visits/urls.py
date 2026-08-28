"""Visits URLs."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from sil_advantage.visits import views

router = SimpleRouter()
router.register("visits", views.VisitViewSet)
router.register("queues", views.QueueViewSet)
router.register("service_requests", views.ServiceRequestViewSet)
router.register("survey_responses", views.SurveyResponseViewSet)

urlpatterns = router.urls
urlpatterns += (
    path(
        "visits/<uuid:id>/transition/<slug:status>/",
        views.VisitTransitionView.as_view(),
        name="visit-transition",
    ),
)
