"""Test random password."""
from unittest import TestCase

from sil_advantage.sil_auth.auth_utils import generate_rand_password


class TestAuthUtils(TestCase):
    """Test case for auth utils."""

    def test_rand_password(self):
        """Test to generate a random password."""
        passwd = generate_rand_password(7)
        assert len(passwd) == 7
        assert isinstance(passwd, str)
