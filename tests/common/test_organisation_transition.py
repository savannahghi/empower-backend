"""Tests for organisation transition states."""
from django.urls import reverse
from model_bakery import baker

from sil_advantage.common.models import Organisation
from sil_advantage.permissions import perms as perms
from tests.common.test_common_views import LoggedInMixin


class TestOrganisationTransition(LoggedInMixin):
    """Tests for when org changes between active and inactive."""

    def test_transition_success(self):
        """Test successful transition between active and inactive."""
        self.assign_permission([perms.CROSS_NETWORK_ADMIN[0]])
        org = baker.make(Organisation, active=True)
        t_url = reverse(r"organisation-transition", args=(org.id, False))
        t_resp = self.client.patch(t_url, {"note": "Zima Kitu"})
        assert t_resp.status_code == 200
        assert t_resp.data["active"] is False
        l_url = reverse("organisation-transition-history", args=(org.id,))
        logs_resp = self.client.get(l_url)
        assert logs_resp.data["count"] == 1
        assert logs_resp.status_code == 200
        assert logs_resp.data["results"][0]["active_from"] == "True"
        assert logs_resp.data["results"][0]["active_to"] == "False"

    def test_transition_fail(self):
        """Test organisation can't transion state to same state."""
        self.assign_permission([perms.CROSS_NETWORK_ADMIN[0]])
        org = baker.make(Organisation, active=True)
        t_url = reverse(r"organisation-transition", args=(org.id, True))
        t_resp = self.client.patch(t_url, {"note": "Zima Kitu"})
        assert t_resp.status_code == 400
        assert t_resp.data["active"][0] == "True to True is an invalid transition."
        l_url = reverse("organisation-transition-history", args=(org.id,))
        logs_resp = self.client.get(l_url)
        assert logs_resp.data["count"] == 0
        assert logs_resp.status_code == 200

    def test_must_be_network_admin(self):
        """Test only org admin can change the state."""
        org = baker.make(Organisation, active=True)
        t_url = reverse(r"organisation-transition", args=(org.id, True))
        t_resp = self.client.patch(t_url, {"note": "Zima Kitu"})
        assert t_resp.status_code == 403
        assert (
            t_resp.data["detail"]
            == "Permission denied: You must be a network administrator"
            " to perform this action"
        )
        l_url = reverse("organisation-transition-history", args=(org.id,))
        logs_resp = self.client.get(l_url)
        assert logs_resp.data["count"] == 0
        assert logs_resp.status_code == 200

    def test_transition_fail_unknown_transistion(self):
        """Test unknown transition state fails."""
        self.assign_permission([perms.CROSS_NETWORK_ADMIN[0]])
        org = baker.make(Organisation, active=True)
        t_url = reverse(r"organisation-transition", args=(org.id, "Kakitu"))
        t_resp = self.client.patch(t_url, {"note": "Zima Kitu"})
        assert t_resp.status_code == 400
        assert t_resp.data["Kakitu"][0] == "Target workflow state non existent"
        l_url = reverse("organisation-transition-history", args=(org.id,))
        logs_resp = self.client.get(l_url)
        assert logs_resp.data["count"] == 0
        assert logs_resp.status_code == 200
