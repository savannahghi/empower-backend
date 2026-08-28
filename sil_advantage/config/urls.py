"""Main URLs module."""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.decorators.cache import cache_page
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from sil_advantage.common.views import ERPView, HomePageView
from sil_advantage.sil_auth.views import MeView

apipatterns = [
    path("auth/", include("sil_advantage.sil_auth.urls")),
    path("common/", include("sil_advantage.common.urls")),
    path("patients/", include("sil_advantage.patients.urls")),
    path("practitioners/", include("sil_advantage.practitioners.urls")),
    path("scheduling/", include("sil_advantage.scheduling.urls")),
    path("notifications/", include("sil_advantage.notifications.urls")),
    path("visits/", include("sil_advantage.visits.urls")),
    path("billing/", include("sil_advantage.billing.urls")),
    path("settings/", include("sil_advantage.settings.urls")),
    path("integrations/", include("sil_advantage.integrations.urls")),
    path("segments/", include("sil_advantage.segments.urls")),
    path("prescriptions/", include("sil_advantage.prescriptions.urls")),
    path(
        "erp/<path:resource>",
        ERPView.as_view(),
        name="erp",
    ),
]

urlpatterns = [
    path(
        "",
        cache_page(3600)(HomePageView.as_view()),
        name="homepage",
    ),
    path("auth", include("sil_auth_backends.urls")),
    path("api/", include(apipatterns)),  # type: ignore
    path("me/", MeView.as_view(), name="me"),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.ENVIRONMENT == "dev":
    schema_view = get_schema_view(
        openapi.Info(
            title="Advantage API",
            default_version="v1",
            description="API for the Advantage application",
        ),
        public=True,
        permission_classes=(permissions.AllowAny,),
    )

    urlpatterns += [
        path(
            "silk/",
            include("silk.urls", namespace="silk"),
        ),
        path(
            "swagger/",
            schema_view.with_ui("swagger", cache_timeout=0),
            name="schema-swagger-ui",
        ),
        path(
            "redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"
        ),
    ]
