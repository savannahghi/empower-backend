"""Test common filters."""
from datetime import datetime

from django.test.utils import override_settings
from django.utils.timezone import make_aware
from model_bakery import baker

from tests.common.sample_app.models import ABC
from tests.common.test_common_views import LoggedInMixin


@override_settings(ROOT_URLCONF="tests.common.sample_app.urls")
class TestAllDateTimeFilter(LoggedInMixin):
    """Test AllDateTime Filter."""

    test_url = "/abc/"

    def setUp(self):
        """Update test environment."""
        super().setUp()
        # use year-month-day
        tenee_sana = make_aware(datetime.strptime("2008-01-12", "%Y-%m-%d"))
        tenee_kidogo = make_aware(datetime.strptime("2010-11-15", "%Y-%m-%d"))
        karibu = make_aware(datetime.strptime("2016-08-25", "%Y-%m-%d"))
        mbali = make_aware(datetime.strptime("2020-01-12", "%Y-%m-%d"))
        mbali_sana = make_aware(datetime.strptime("2036-12-01", "%Y-%m-%d"))

        baker.make(
            ABC,
            jina="John Cena",
            siku=tenee_sana,
        )
        baker.make(
            ABC,
            jina="Batista",
            siku=tenee_kidogo,
        )
        baker.make(
            ABC,
            jina="Shawn Michaels",
            siku=karibu,
        )
        baker.make(
            ABC,
            jina="Undertaker",
            siku=mbali,
        )
        baker.make(
            ABC,
            jina="Jericho",
            siku=mbali_sana,
        )

    def test_datetime_filtering_using_formats_specified(self):
        """Test datetime filtering using supported formats."""
        # use ISO 8601
        resp = self.client.get(
            self.test_url,
            {
                "from_date": "2008-01-01T00:00:00",
                "to_date": "2017-01-01T00:00:00",
            },
        )
        assert resp.status_code == 200
        assert resp.data["count"] == 3

        # use %Y-%m-%d
        resp = self.client.get(
            self.test_url, {"from_date": "2010-08-15", "to_date": "2017-01-01"}
        )
        assert resp.status_code == 200
        assert resp.data["count"] == 2

        # use %Y/%m/%d
        resp = self.client.get(
            self.test_url, {"from_date": "2009/08/15", "to_date": "2040/01/12"}
        )
        assert resp.status_code == 200
        assert resp.data["count"] == 4

        # use %d-%m-%Y %H:%M
        resp = self.client.get(
            self.test_url,
            {"from_date": "25-10-2006 14:30", "to_date": "25-10-2011 14:30"},
        )
        assert resp.status_code == 200
        assert resp.data["count"] == 2

        # use %d/%m/%Y %H:%M:%S
        resp = self.client.get(
            self.test_url,
            {
                "from_date": "25/10/2006 14:30:30",
                "to_date": "25/10/2040 14:30:27",
            },
        )
        assert resp.status_code == 200
        assert resp.data["count"] == 5

    def test_datetime_filtering_using_unsupported_formats(self):
        """Test datetime filtering using unsupported formats."""
        # use %Y %m %d
        resp = self.client.get(
            self.test_url, {"from_date": "2008 01 01", "to_date": "2017 01 01"}
        )
        assert resp.status_code == 400, (resp.status_code, resp.content)

        # use %m-%d-%Y
        resp = self.client.get(
            self.test_url, {"from_date": "12-25-2011", "to_date": "12-25-2018"}
        )
        assert resp.status_code == 400, (resp.status_code, resp.content)
