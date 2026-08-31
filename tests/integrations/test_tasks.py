"""Test integrations tasks."""
from unittest.mock import patch

from model_bakery import baker
from sil_monitoring import Monitor

from sil_advantage.billing.models import Invoice
from sil_advantage.common.models import Organisation
from sil_advantage.common.tasks import (
    setup_periodic_tasks,
    sync_org_updates_with_remote,
)
from sil_advantage.config import celery_app
from sil_advantage.integrations.tasks import (
    report_sync_linking_stats,
    sync_updates_to_remote,
)
from sil_advantage.patients.models import Patient
from sil_advantage.visits.models import Queue, Visit
from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.integrations.tasks."


class TestSyncTasks(LoggedInMixin):
    """Test Sync Tasks."""

    def setUp(self) -> None:
        """Set up test environment."""
        super().setUp()
        patient = baker.make(
            Patient,
            organisation=self.global_organisation,
        )
        queue = baker.make(Queue)
        baker.make(
            Visit,
            patient=patient,
            current_queue=queue,
            status="ARRIVED",
            organisation=self.global_organisation,
        )
        self.invoice = Invoice.objects.latest("created")

    def test_registering_scheduling_tasks(self):
        """Test registering tasks with Celery."""
        setup_periodic_tasks()
        assert (
            "sil_advantage.integrations.files.google_drive.open_google_drive_channels"
            in celery_app.tasks
        )
        assert (
            "sil_advantage.integrations.tasks.report_sync_linking_stats"
            in celery_app.tasks
        )

    @patch(MOCK_ROOT + "LOGGER")
    def test_sync_attempt_with_invalid_system(self, mock_logger):
        """Test sync attempt with an invalid system."""
        sync_updates_to_remote(
            "billing.invoice",
            self.invoice.pk,
            "MARKETPLACE",
            "CREATE",
        )
        mock_logger.error.assert_called_once_with("Unsupported system MARKETPLACE.")

    @patch.object(Monitor, "gauge")
    def test_reporting_sync_linking_stats_to_grafana(self, mock_monitor_gauge):
        """Test reporting sync linking stats to Grafana."""
        report_sync_linking_stats()

        assert mock_monitor_gauge.call_count == 13
        mock_monitor_gauge.assert_called_with(
            "unlinked_objects",
            1,
            tags={
                "model": "visits.servicerequest",
                "remote": "CLINICAL_SERVICE",
            },
        )

    @patch.object(Organisation, "create_queues_for_workstations")
    @patch.object(Organisation, "create_facilities_on_clinical_server")
    def test_sync_org_updates_with_remote(
        self,
        mock_create_facilities,
        mock_create_queues,
    ):
        """Test syncing organisation updates with remote."""
        sync_org_updates_with_remote()

        mock_create_facilities.assert_called()
        mock_create_queues.assert_called()
