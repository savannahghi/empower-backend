"""Test for common models in the application."""
import datetime
from unittest.mock import patch

import pytest
from django.test import override_settings
from model_bakery import baker
from sil_erp_client.client import ERP, ApiConnection
from sil_wrapper_utils.exceptions import ItemNotFound

from sil_advantage.common.models import Organisation
from tests.common.utility import PicklableMagicMock


@pytest.mark.django_db
@override_settings(
    SYNC_WITH_PROVIDER_IS=True,
    SYNC_WITH_ERP=True,
    ERP_API_CONFIG={
        "api_host": "uat-invoice-discounting-api.healthcloud.co.ke/api",
        "api_scheme": "https",
        "oauth_client_id": "1oauth-client-id",
        "oauth_client_secret": "2oauth-client-secret",
        "user_email": "erp.testing@slade360.co.ke",
        "user_password": "avErYsecurepa33w0rd",
        "token_url": "https://authserver.multitenant.slade360.co.ke/oauth2/token/",
    },
)
@patch.object(ERP, "currencies", create=True)
@patch.object(ERP, "customers", create=True)
@patch.object(ERP, "workstations", create=True)
@patch.object(ERP, "organisations", create=True)
@patch.object(
    ApiConnection, "credentials", create=True, new_callable=PicklableMagicMock
)
@patch.object(ApiConnection, "_get_token")
def test_sync_with_erp_on_save_no_currency(
    mock_erp_auth,
    mock_credz,
    mock_erp_orgs,
    mock_erp_workstations,
    mock_erp_customers,
    mock_erp_currencies,
    mock_provider_is,
):
    """Test Organisation sync with ERP."""

    def get_erp_org(filter):
        if filter["slade_code"] == 1:
            return {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"}
        else:
            raise ItemNotFound("Org not found")

    mock_erp_orgs.get_with.side_effect = get_erp_org
    mock_credz.__getitem__.return_value = "435wersgfs45t"
    mock_erp_orgs.setup_organisation.return_value = {
        "id": "8f114393-bc23-4920-85e5-95b12150846c",
    }
    mock_erp_customers.get_with().__getitem__.return_value = None
    mock_erp_currencies.list.return_value = {"results": []}

    def mocked_erp_init(
        self,
        api_host,
        api_scheme,
        oauth_client_id,
        oauth_client_secret,
        user_email,
        user_password,
        token_url,
        scopes=None,
        auth_retries=3,
        auth_retry_delay=1,
        timeout_retries=6,
        timeout_retry_delay=10,
    ):
        self.conn = ApiConnection(
            host=api_host,
            oauth_id=oauth_client_id,
            oauth_secret=oauth_client_secret,
            user_email=user_email,
            user_password=user_password,
            scheme=api_scheme,
            token_url=token_url,
            scopes=scopes,
            auth_retries=auth_retries,
            auth_retry_delay=auth_retry_delay,
            timeout_retries=timeout_retries,
            timeout_retry_delay=timeout_retry_delay,
        )

    with patch.object(ERP, "__init__", mocked_erp_init):
        # Create organisation, not on ERP
        org = baker.make(
            Organisation,
            slade_code=12389,
            organisation_name="Oregon Health Demo",
            email_address="oregon@slade360.co.ke",
            phone_number="+254712345678",
            description="",
            postal_address="15-10100",
            physical_address="Kimathi Way",
            default_country="KEN",
            financial_year_start_date=datetime.date(2022, 1, 1),
        )
        org.save()
        mock_erp_currencies.list.return_value = {"results": None}
        mock_erp_customers.reset_mock(side_effect=True)
        mock_erp_customers.get_with.side_effect = ItemNotFound("404")

        """assert provider IS creation."""
        mock_provider_is.business_partners.create_site_settings.assert_called_with(
            slade_code=12389
        )

        with pytest.raises(ValueError) as excinfo:
            org.create_customer_on_erp()

        assert str(excinfo.value) == "Invalid Currency: Default currency not found."
