"""Notifications URLs."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from sil_advantage.notifications import views
from sil_advantage.notifications.sms import views as sms_views
from sil_advantage.notifications.ussd.views import ussd_view

router = SimpleRouter()
router.register("groups", views.GroupViewSet)
router.register("group_members", views.GroupMemberViewSet)
router.register("sender_ids", sms_views.SenderIDViewset)
router.register("sms", sms_views.SMSViewSet)
router.register("sms_log_report", sms_views.SMSLogReportViewSet)

urlpatterns = router.urls
urlpatterns += (
    path(
        "send_sms/",
        sms_views.SendSMSView.as_view(),
        name="send-sms",
    ),
    path("ussd/", ussd_view, name="ussd_view"),
    path(
        "interactive-shortcode-callback/",
        sms_views.SMSViewSet.as_view({"post": "interactive_shortcode_callback"}),
        name="interactive-shortcode-callback",
    ),
)
