"""Define utilities used in test."""
from dataclasses import dataclass
from functools import partial
from typing import Generic, TypeVar
from unittest.mock import MagicMock, patch

from model_bakery import baker

T = TypeVar("T")


class PicklableMagicMock(MagicMock):
    """Picklable MagicMock."""

    def __reduce__(self):
        """Reduce."""
        return (MagicMock, ())


class AsyncMagicMock(MagicMock):
    """Async MagicMock."""

    async def __call__(self, *args, **kwargs):
        """Convert the call to async."""
        return super().__call__(*args, **kwargs)


@dataclass
class QuintusReponse:
    """Quintus Response."""

    text: str = None
    data: dict = None

    def json(self):
        """Get the JSON representation."""
        return self.data

    def mocked_login(*args, **kwargs):
        """Mock loggin in to Quintus."""
        return QuintusReponse(text="a jwt token")


def mock_baker(values):
    """Create test fixture."""
    assert isinstance(values, dict), (
        "Expects " "{field_name, field_value} dict. " f"Found {type(values)}"
    )

    class _Baker(baker.Baker, Generic[T]):
        fields = values

        def _get_field_names(self):
            return [each.name for each in self.get_fields()]

        def _make(self, *args, **attrs):
            for field_name, value in self.fields.items():
                if field_name in self._get_field_names():
                    attrs.setdefault(field_name, value)
            return super()._make(*args, **attrs)

    return _Baker


patch_baker = partial(patch, "model_bakery.baker.Baker", new_callable=mock_baker)


def make_transitions(obj, transitions, note=dict):
    """Change state of organisation."""
    for each in transitions:
        obj.workflow_state = each
        obj.transition(note)
    return obj
