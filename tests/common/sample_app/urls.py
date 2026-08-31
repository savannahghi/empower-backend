"""Sample app URLs."""
from rest_framework import routers

from . import views

router = routers.SimpleRouter()
router.register("abc", views.ABCViewSet)

urlpatterns = router.urls
