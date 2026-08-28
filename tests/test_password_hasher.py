"""Tests for password hasher."""
from django.contrib.auth.hashers import PBKDF2PasswordHasher


class PBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """Test password hasher.

    A subclass of PBKDF2PasswordHasher that
    makes only one iteration for speed.
    """

    iterations = 1
