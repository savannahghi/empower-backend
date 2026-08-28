"""Test common misc utils."""
from unittest.mock import patch

from django.test import SimpleTestCase

from sil_advantage.common.utilities.misc import shorten_url

MOCK_ROOT = "sil_advantage.common.utilities."


class TestUtilities(SimpleTestCase):
    """Test common utilities."""

    @patch(MOCK_ROOT + "misc.pyshorteners")
    def test_shorten_url_link(self, mock_tinyurl):
        """Test shortening url link."""
        expected_url = "https://tinyurl.com/yu9stpcs"
        mock_tinyurl.Shortener().tinyurl.short.return_value = expected_url

        url = "https://advantage.slade360.com/some/very/long/url"
        short_url = shorten_url(url)
        assert short_url == expected_url
