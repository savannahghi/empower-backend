"""This module contains tests for the URL shortener utility functions."""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from sil_shlink import ShlinkPayload

from sil_advantage.common.utilities.urlshortener import shlink_shorten_url


class ShlinkShortenURL(TestCase):
    """Class to test the shlink_shorten_url function."""

    @patch("sil_advantage.common.api_clients.shlink.get_shlink_client")
    def test_shlink_shorten_url_success(self, mock_get_shlink_client):
        """Test successful URL shortening using the shlink_shorten_url function."""
        mock_client = MagicMock()
        mock_client.shorten_url.return_value = {
            "shortUrl": "https://e.slade360.com/fmpSv"
        }
        mock_get_shlink_client.return_value = mock_client

        payload = ShlinkPayload(
            long_url="https://example.com", domain="https://e.slade360.com"
        )
        result = shlink_shorten_url(payload)
        self.assertEqual(result, "https://e.slade360.com/fmpSv")

    def test_shlink_shorten_url_failure_invalid_url(
        self,
    ):
        """Test URL shortening failure due to an invalid URL."""
        payload = ShlinkPayload(long_url="")
        with self.assertRaises(ValueError) as context:
            shlink_shorten_url(payload)
        self.assertTrue("URL to shorten is required." in str(context.exception))

    def test_shlink_shorten_url_invalid_payload_type(self):
        """Test URL shortening failure due to invalid payload type."""
        invalid_payload = "This is not a valid ShlinkPayload object"
        with self.assertRaises(ValueError) as context:
            shlink_shorten_url(invalid_payload)
        self.assertTrue("Invalid payload provided." in str(context.exception))

    @patch("sil_advantage.common.api_clients.shlink.get_shlink_client")
    def test_shlink_shorten_url_failure_exception(self, mock_get_shlink_client):
        """Test URL shortening failure due to an exception."""
        mock_client = MagicMock()
        mock_client.shorten_url.side_effect = Exception("Something went wrong")
        mock_get_shlink_client.return_value = mock_client

        payload = ShlinkPayload(long_url="https://example.com")
        with self.assertRaises(Exception) as context:
            shlink_shorten_url(payload)
        self.assertTrue("Something went wrong" in str(context.exception))

    @patch("sil_advantage.common.api_clients.shlink.get_shlink_client")
    def test_shlink_shorten_url_default_domain(self, mock_get_shlink_client):
        """Test that the default domain is used when payload domain is None or empty."""
        mock_client = MagicMock()
        mock_client.shorten_url.return_value = {
            "shortUrl": "https://custom.domain/fmpSv"
        }
        mock_get_shlink_client.return_value = mock_client

        payload_none_domain = ShlinkPayload(long_url="https://example.com", domain=None)
        result_none_domain = shlink_shorten_url(payload_none_domain)
        self.assertEqual(result_none_domain, "https://custom.domain/fmpSv")

        payload_empty_domain = ShlinkPayload(long_url="https://example.com", domain="")
        result_empty_domain = shlink_shorten_url(payload_empty_domain)
        self.assertEqual(result_empty_domain, "https://custom.domain/fmpSv")
