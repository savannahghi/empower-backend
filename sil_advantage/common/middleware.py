"""Middleware."""
import re
from typing import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from sil_monitoring import Monitor
from sil_monitoring.backends import StatsD


class LatencyMiddleware:
    """Middleware to track latency."""

    def __init__(self, get_response: Callable) -> None:
        """Initialize middleware."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Export latency to StatsD."""
        monitor = Monitor(
            StatsD(
                settings.STATSD_HOST,  # type: ignore  # import cycle issue
                settings.STATSD_PORT,  # type: ignore  # import cycle issue
                backend="telegraf",
            )
        )

        if request.path == "/":
            # Don't collect metrics for k8s liveness probes
            # since they're skewing our metrics
            return self.get_response(request)
        else:
            path = re.sub(
                r"/[\da-f]{8}-([\da-f]{4}-){3}[\da-f]{12}/",
                "/<uuid>/",
                request.path.replace("/api/", "/"),
            )
            tags = {"method": request.method, "path": path}
            with monitor.timer("api_latency", tags=tags):
                response: HttpResponse = self.get_response(request)
                tags["status_code"] = str(response.status_code)
                return response
