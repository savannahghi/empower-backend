"""Scheduling URLs."""
from rest_framework.routers import SimpleRouter

from sil_advantage.scheduling import views

router = SimpleRouter()
router.register("schedules", views.ScheduleView, "schedules")
router.register(
    "schedule_timings",
    views.ScheduleTimingView,
    "schedule_timings",
)
router.register("slots", views.SlotView, "slots")
router.register(
    "appointments",
    views.AppointmentView,
    "appointments",
)

urlpatterns = router.urls
