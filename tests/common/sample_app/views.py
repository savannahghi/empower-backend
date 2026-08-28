"""Test sample app views."""
from rest_framework import viewsets
from rest_framework.decorators import action

from sil_advantage.common.utilities import paginate_response

from . import filters, models, serializers


class BaseView(viewsets.ModelViewSet):
    """Allow the viewset to work with list and detail serializers.

    Allows the view to work with two serializers : one for the list view
    and another for the detail view.
    This is particularly helpful when inlining ManyToMany and foreign key
    records.
    """

    _list_serializer_class = None
    _detail_serializer_class = None
    list_actions = ["list"]

    def get_serializer_class(self):
        """Pick serializer class to use."""
        if self._list_serializer_class and self.action in self.list_actions:
            return self._list_serializer_class
        elif self._detail_serializer_class:
            return self._detail_serializer_class
        else:
            return super().get_serializer_class()

    def get_serializer(self, *args, **kwargs):
        """Pick serializer to use."""
        if "data" in kwargs:
            data = kwargs["data"]
            if isinstance(data, list):
                kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)


class ABCViewSet(BaseView):
    """ABC Viewset."""

    queryset = models.ABC.objects.all()
    _list_serializer_class = serializers.ABCSerializer
    _detail_serializer_class = serializers.ABCDetailSerializer
    filterset_class = filters.ABCFilter

    @action(methods=("get",), detail=False)
    def my_list(self, request, *args, **kwargs):
        """List ABCs."""
        qs = models.ABC.objects.order_by("-siku")
        return paginate_response(self, qs)
