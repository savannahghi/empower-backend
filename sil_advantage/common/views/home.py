"""General project views e.g error and home views."""
from typing import Any

from django.views.generic import TemplateView
from rest_framework.permissions import AllowAny

from sil_advantage import __version__
from sil_advantage.config.settings import TEMPLATES

TEMPLATE_DIRS = TEMPLATES[0]["DIRS"]


class HomePageView(TemplateView):
    """Simple Advantage API homepage."""

    template_name = "home.html"
    authentication_classes: list[str] = []
    permission_classes = (AllowAny,)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add Home Page context."""
        context = super().get_context_data(**kwargs)
        context["VERSION"] = __version__
        return context
