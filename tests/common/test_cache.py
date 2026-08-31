"""Test cache."""
from django.core.cache import cache

from sil_advantage.common.cache import cached


@cached
def foo():
    """Foo."""
    return "bar"


@cached(cache_falsy=False)
def picky_foo():
    """Picky foo."""
    return False


def test_caching_normally():
    """Test caching."""
    assert cache.get("5a1f89c79382b848dfab471f1815448c") is None
    assert foo() == "bar"
    assert cache.get("5a1f89c79382b848dfab471f1815448c") == "bar"
    assert foo() == "bar"


def test_caching_falsy_values_ignored():
    """Test caching while ignoring falsy values."""
    assert cache.get("367e39e0e2c41e668ba949c710308c07") is None
    assert picky_foo() is False
    assert cache.get("367e39e0e2c41e668ba949c710308c07") is None
    assert picky_foo() is False
