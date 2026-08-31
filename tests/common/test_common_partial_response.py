"""Request object used for mocking."""
from django.urls import reverse
from model_bakery import baker

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.common.serializers.base import PartialResponseMixin
from sil_advantage.patients.models import Patient
from tests.common.test_common_views import LoggedInMixin


# These are mock request objects
# They could have been created with the ``mock`` library but are created
# this way for didactic reasons
class MockEmptyRequest:
    """Mock empty request i.e no method and parameters."""

    pass


class MockPostRequest:
    """Mocks POST method with empty parameters."""

    method = "POST"
    query_params = {}


class MockRequestNoMethodHasQueryParams:
    """Mock request has empty parameters without method."""

    query_params = {}


class MockGetRequestNoFields:
    """Mocks GET method with empty parameters."""

    method = "GET"
    query_params = {}


class MockGetWithStringFields:
    """Mocks GET method with string parameters(no space)."""

    method = "GET"
    query_params = {"fields": "id,name,description"}


class MockGetWithPaddedStringFields:
    """Mocks GET method with string parameters(spaced)."""

    method = "GET"
    query_params = {"fields": "id, name, description"}


class MockGetWithNonStringFields:
    """Mocks GET method with integer parameters."""

    method = "GET"
    query_params = {"fields": (1, 2, 3)}


class MockField:
    """Defines the mockfield."""

    dummy_marker = "dummy"

    def __eq__(self, other):
        """Compare if equal to defined dummy marker."""
        return self.dummy_marker == other.dummy_marker


class PartialResponseTest(LoggedInMixin):
    """Test suite for testing partial response."""

    def setUp(self):
        """Set up a request mock for the partial response test.

        The request mock is an object that meets the following criteria:
         * it should have a ``method`` attribute. This ``method`` can be
         either ``GET`` or anything else e.g ``POST``
         * it should have a ``query_params`` attribute, which is itself a
         dictionary. That dictionary may or may not have a ``fields`` key
        It also sets up an ``origi_fields`` variable that is a dictionary
        """
        super().setUp()
        self.maxDiff = None  # See full diff in test failure report
        self.test_mixin = PartialResponseMixin()
        self.mock_field = MockField()
        self.empty_request = MockEmptyRequest()
        self.post_request = MockPostRequest()
        self.request_queryparams_nomethod = MockRequestNoMethodHasQueryParams()
        self.get_request_no_fields = MockGetRequestNoFields()
        self.get_request_with_string_fields = MockGetWithStringFields()
        self.get_request_with_padded_fields = MockGetWithPaddedStringFields()
        self.get_request_with_non_string_fields = MockGetWithNonStringFields()
        self.original_fields = {"id": MockField(), "name": MockField()}

    def test_that_original_fields_are_returned_for_null_requests(self):
        """Test null requests.

        If a 'None' request and an ``original_fields`` list are passed in,
        expect to get back the ``original_fields`` unchanged

        """
        string_1 = self.test_mixin.strip_fields(None, self.original_fields)
        string_2 = self.original_fields

        assert string_1 == string_2

    def test_that_with_a_post_method_original_fields_returned(self):
        """Test with a post method.

        If an request with a method 'POST' ( not 'GET' ) is passed in
        alongside a list of fields, the list of fields should be returned
        unaltered. This verifies that the mixin only alters GETs

        """
        param_1 = self.post_request
        param_2 = self.original_fields

        string_1 = self.test_mixin.strip_fields(param_1, param_2)
        string_2 = self.original_fields

        assert string_1 == string_2

    def test_that_a_request_with_no_methods_original_fields_returned(self):
        """Test with no original field.

        If a request object with no 'method' attr is passed in, the original
        fields should not be altered. This verifies that the mixin has sane
        fallback behavior - i.e. it defaults to not altering fields

        """
        param_1 = self.empty_request
        param_2 = self.original_fields

        string_1 = self.test_mixin.strip_fields(param_1, param_2)
        string_2 = self.original_fields

        assert string_1 == string_2

    def test_request_with_query_params_no_method_origi_fields_returned(self):
        """Test with passed parameters.

        If a request with a query params dict but no method is passed in,
        the original_fields should remain unaltered

        """
        param_1 = self.request_queryparams_nomethod
        param_2 = self.original_fields

        string_1 = self.test_mixin.strip_fields(param_1, param_2)
        string_2 = self.original_fields

        assert string_1 == string_2

    def test_request_with_a_get_method_and_no_fields_is_not_altered(self):
        """Test post method without passed parameters.

        If a request object has a 'GET' method but its ``query_params`` dict
        has no ``fields`` key, the original_fields should not be altered

        """
        param_1 = self.get_request_no_fields
        param_2 = self.original_fields

        string_1 = self.test_mixin.strip_fields(param_1, param_2)
        string_2 = self.original_fields

        assert string_1 == string_2

    def test_request_with_get_method_and_non_string_fields_is_unaltered(self):
        """Test get method.

        If a request object has a 'GET' method, its 'query_params' have a
        'fields' key but the 'fields' value is NOT a string, return the
        original_fields unaltered

        """
        param_1 = self.get_request_with_non_string_fields
        param_2 = self.original_fields

        string_1 = self.test_mixin.strip_fields(param_1, param_2)
        string_2 = self.original_fields

        assert string_1 == string_2

    def test_request_with_get_method_and_comma_separated_string_fields(self):
        """Test get method with comma.

        For a request with a GET method and a comma separated field list, the
        field list will be split on the comma and the resulting strings
        returned in a dict

        """
        param_1 = self.get_request_with_string_fields
        param_2 = self.original_fields

        string_1 = self.test_mixin.strip_fields(param_1, param_2)
        string_2 = {"id": MockField(), "name": MockField()}
        assert string_1 == string_2

    def test_comma_separated_list_with_spaces_handled_correctly(self):
        """Test comma separated list with spaces request.

        For a request with a GET method and a comma separated field list that
        includes spaces around the commas, the field list will still be split
        correctly around the comma, with padding spaces discarded.

        """
        param_1 = self.get_request_with_padded_fields
        param_2 = self.original_fields

        string_1 = self.test_mixin.strip_fields(param_1, param_2)
        string_2 = {"id": MockField(), "name": MockField()}

        assert string_1 == string_2

    def test_partial_response_filter_prefetch(self):
        """Test partial response filter prefetch."""
        url = reverse("patient-list")
        person = baker.make(
            Person,
            first_name="Stephen",
            last_name="Mwangi",
            organisation=self.global_organisation,
        )
        baker.make(
            PersonContact,
            contact_type=iter(["phone_number", "email"]),
            contact=iter(["+254790360360", "stephen@example.com"]),
            is_primary_contact=True,
            person=person,
            organisation=self.global_organisation,
            _quantity=2,
        )
        self.patient = baker.make(
            Patient, person=person, organisation=self.global_organisation
        )

        # no select & prefetch related
        response = self.client.get(url + "?fields=file_number")
        result = response.json()["results"][0]
        assert len(result) == 1
        assert result["file_number"] == 1
        assert "person" not in result

        # select related person
        response = self.client.get(url + "?fields=file_number,person")
        result = response.json()["results"][0]
        assert len(result) == 2
        assert result["person"]["first_name"] == "Stephen"
