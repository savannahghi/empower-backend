"""Test data partitioning."""
import uuid
from itertools import cycle

from django.urls import reverse
from model_bakery import baker
from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIRequestFactory, force_authenticate

from sil_advantage.common.models import Organisation
from sil_advantage.patients.models import Patient
from sil_advantage.patients.views import PatientViewSet
from sil_advantage.permissions import perms
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin


class DataPartitioningTest(LoggedInMixin):
    """Test data partitioning."""

    patients_list_url = reverse("patient-list")

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        assert Patient.objects.all().count() == 0

        self.headers = {
            "X-Cluster": uuid.uuid4(),
            "X-Branch": uuid.uuid4(),
            "X-Department": uuid.uuid4(),
            "X-Workstation": uuid.uuid4(),
        }

        self.org2_id = uuid.uuid4()
        org2 = baker.make(
            Organisation,
            id=self.org2_id,
            organisation_name="AKUH",
            slade_code=125,
        )

        baker.make(
            Patient,
            organisation=self.global_organisation,
            cluster_id=cycle(
                [
                    self.headers["X-Cluster"],
                    self.headers["X-Cluster"],
                    self.headers["X-Cluster"],
                    self.headers["X-Cluster"],
                    uuid.uuid4(),
                ]
            ),
            branch_id=cycle(
                [
                    self.headers["X-Branch"],
                    self.headers["X-Branch"],
                    self.headers["X-Branch"],
                    uuid.uuid4(),
                    uuid.uuid4(),
                ]
            ),
            department_id=cycle(
                [
                    self.headers["X-Department"],
                    self.headers["X-Department"],
                    uuid.uuid4(),
                    uuid.uuid4(),
                    uuid.uuid4(),
                ]
            ),
            workstation_id=cycle(
                [
                    self.headers["X-Workstation"],
                    uuid.uuid4(),
                    uuid.uuid4(),
                    uuid.uuid4(),
                    uuid.uuid4(),
                ]
            ),
            _quantity=5,
        )
        baker.make(Patient, organisation=org2, _quantity=3)

    def test_data_partitioning_super_admin(self):
        """Test data partitioning when logged in as a cluster admin."""
        self.make_user_super_admin()
        self.headers["HTTP_USER_AGENT"] = "Advantage Backend"
        response = self.client.get(self.patients_list_url, **self.headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 5

    def test_data_partitioning_organisation_admin(self):
        """Test data partitioning when logged in as an org admin."""
        self.make_user_org_admin()
        response = self.client.get(self.patients_list_url, **self.headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 5

    def test_data_partitioning_cluster_admin(self):
        """Test data partitioning when logged in as a cluster admin."""
        self.assign_permission([perms.CLUSTER_ADMIN[0]])
        PatientViewSet._data_partition_field = "cluster_id"
        view = PatientViewSet.as_view({"get": "list"})
        request = APIRequestFactory().get("", **self.headers)
        force_authenticate(request, user=self.user)
        response = view(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 4

    def test_data_partitioning_branch_admin(self):
        """Test data partitioning when logged in as a branch admin."""
        self.assign_permission([perms.BRANCH_ADMIN[0]])
        PatientViewSet._data_partition_field = "branch_id"
        view = PatientViewSet.as_view({"get": "list"})
        request = APIRequestFactory().get("", **self.headers)
        force_authenticate(request, user=self.user)
        response = view(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 3

    def test_department_level_data_partitioning(self):
        """Test data partitioning at the department level."""
        PatientViewSet._data_partition_field = "department_id"
        view = PatientViewSet.as_view({"get": "list"})
        request = APIRequestFactory().get("", **self.headers)
        force_authenticate(request, user=self.user)
        response = view(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2

    def test_workstation_level_data_partitioning(self):
        """Test data partitioning at the workstation level."""
        PatientViewSet._data_partition_field = "workstation_id"
        view = PatientViewSet.as_view({"get": "list"})
        request = APIRequestFactory().get("", **self.headers)
        force_authenticate(request, user=self.user)
        response = view(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1

    def test_workstation_headers_provided(self):
        """Test that workstation headers are provided."""
        response = self.client.post(
            self.patients_list_url,
            data={
                "person": {
                    "first_name": "Stephen",
                    "last_name": "Mwangi",
                    "person_contacts": [],
                    "person_ids": [],
                    "person_photos": [],
                }
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == [
            ErrorDetail(
                string=(
                    "Please provide the following headers: "
                    "X-Cluster, X-Branch, X-Department, & X-Workstation."
                ),
                code="invalid",
            )
        ]
