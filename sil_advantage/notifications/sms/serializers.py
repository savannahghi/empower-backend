"""SMS serializers."""
from rest_framework import serializers

from sil_advantage.common.serializers.base import BaseSerializer
from sil_advantage.notifications.sms import SMS_INTENTIONS
from sil_advantage.notifications.sms.models import SMS, SenderID, SMSLogReport


class SMSInputSerializer(serializers.Serializer):
    """SMS Input Serializer."""

    intention = serializers.ChoiceField(choices=SMS_INTENTIONS)
    recipients = serializers.ListField(
        child=serializers.CharField(max_length=15),
    )
    message = serializers.CharField(max_length=500)


class SenderIDSerializer(BaseSerializer):
    """SenderID Serializer."""

    disabled = serializers.DictField(read_only=True)

    class Meta:
        """Serializer options."""

        model = SenderID
        fields = "__all__"


class SMSSerializer(BaseSerializer):
    """SMS Serializer."""

    sender = SenderIDSerializer(read_only=True)
    from_field = serializers.CharField(source="from_name", read_only=True)
    to_field = serializers.CharField(source="to", read_only=True)

    class Meta:
        """Serializer options."""

        model = SMS
        fields = "__all__"


class SMSLogReportInputSerializer(serializers.Serializer):
    """SMSReport Input Serializer."""

    date_to = serializers.DateField()
    date_from = serializers.DateField()
    delivery_type = serializers.CharField(required=False)


class SMSLogReportSerializer(BaseSerializer):
    """SMSReport Serializer."""

    file_name = serializers.CharField(source="report_file.title", read_only=True)
    report_file_url = serializers.URLField(
        source="report_file.data.url", read_only=True
    )

    class Meta:
        """Serializer options."""

        model = SMSLogReport
        fields = "__all__"
