"""SMS endpoints."""
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.views import APIView

from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.common.views.base import CacheableBaseView
from sil_advantage.notifications.sms import filters, serializers, tasks, utils
from sil_advantage.notifications.sms.models import SMS, SenderID, SMSLogReport
from sil_advantage.permissions import perms, scopes


class SendSMSView(APIView):
    """View to send an SMS."""

    permission_classes = (IsAuthenticated,)

    def post(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """View to send an SMS."""
        serializer = serializers.SMSInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.data
        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")
        org = request.user.organisation
        (
            can_send,
            err,
            _,
            _,
            _,
        ) = utils.can_send_sms(
            org,
            branch_id,
            payload["intention"],
            payload["message"],
            len(payload["recipients"]),
        )
        if not can_send:
            raise ValidationError(err)

        # pick 1st 2 names
        org_name = " ".join(org.organisation_name.split(" ")[:2])
        message = payload["message"].strip() + f" ~ {org_name}"

        workstation_id = request.META.get("HTTP_X_WORKSTATION") or request.META.get(
            "X-Workstation"
        )

        sender_id = utils.get_branch_sender_id(org, branch_id, payload["intention"])

        tasks.send_sms.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(
                payload["intention"],
                message,
                payload["recipients"],
                org.slade_code,
                branch_id,
                workstation_id,
            ),
            kwargs={"sender_id": sender_id},
        )

        return Response("OK", status=status.HTTP_200_OK)


class SenderIDViewset(CacheableBaseView):
    """SenderID viewset."""

    permissions = {
        "GET": [perms.SENDER_ID_VIEW],
        "POST": [perms.SENDER_ID_CREATE],
        "PATCH": [perms.SENDER_ID_EDIT],
        "DELETE": [perms.SENDER_ID_DELETE],
    }
    scopes = {
        "GET": [scopes.SENDER_ID_READ],
        "POST": [scopes.SENDER_ID_WRITE],
        "PATCH": [scopes.SENDER_ID_WRITE],
        "DELETE": [scopes.SENDER_ID_WRITE],
    }

    queryset = SenderID.objects.all()
    serializer_class = serializers.SenderIDSerializer
    filterset_class = filters.SenderIDFilter
    search_fields = ("name",)

    def list(self, request: AuthenticatedRequest) -> Response:
        """Returns default sender ids for Orgs that don't have."""
        queryset = self.filter_queryset(self.get_queryset())

        sender_ids_qs = SenderID.objects.filter(organisation=request.user.organisation)
        if not queryset and not sender_ids_qs.exists():
            senders = [
                settings.SIL_COMMS_TRANSACTIONAL_SENDER_ID,
                settings.SIL_COMMS_PROMOTIONAL_SENDER_ID,
            ]
            queryset = SenderID.objects.filter(name__in=senders, active=True)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class SMSViewSet(CacheableBaseView):
    """SMS viewset."""

    permissions = {
        "GET": [perms.SMS_VIEW],
        "POST": [],
        "PATCH": [],
        "DELETE": [],
    }
    scopes = {
        "GET": [scopes.SMS_READ],
        "POST": [],
        "PATCH": [],
        "DELETE": [],
    }

    queryset = SMS.objects.all()
    filterset_class = filters.SMSFilter
    serializer_class = serializers.SMSSerializer
    search_fields = ("recipients", "message", "sender__name")

    @action(
        detail=False,
        methods=["POST"],
    )
    def generate_sms_log_report(self, request: AuthenticatedRequest) -> Response:
        """Generates an Excel type SMS log report."""
        serializer = serializers.SMSLogReportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.data

        workstation_id = request.META.get("HTTP_X_WORKSTATION") or request.META.get(
            "X-Workstation"
        )
        department_id = request.META.get("HTTP_X_DEPARTMENT") or request.META.get(
            "X-Department"
        )
        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")
        cluster_id = request.META.get("HTTP_X_CLUSTER") or request.META.get("X-Cluster")

        common_fields = {
            "organisation": request.user.organisation,
            "created_by": request.user.guid,
            "updated_by": request.user.guid,
            "workstation_id": workstation_id,
            "department_id": department_id,
            "cluster_id": cluster_id,
            "branch_id": branch_id,
        }
        sms_report_obj = SMSLogReport(**common_fields)
        sms_report_obj.save()

        tasks.generate_sms_log_report.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(
                payload,
                sms_report_obj.id,
            ),
        )

        return Response(
            serializers.SMSLogReportSerializer(sms_report_obj).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(
        detail=False,
        permission_classes=[AllowAny],
        methods=["POST"],
        throttle_classes=[],
    )
    def callback(self, request: Request) -> Response:
        """Process an SMS delivery report from SIL Comms."""
        tasks.process_delivery_report.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(request.data,),
        )

        return Response(status=HTTP_200_OK)

    @action(
        detail=False,
        permission_classes=[AllowAny],
        methods=["POST"],
        throttle_classes=[],
        url_path="interactive-shortcode-callback",
    )
    def interactive_shortcode_callback(self, request: Request) -> Response:
        """Process an interactive shortcode SMS response from SIL Comms."""
        data = request.data.get("data", {})
        msisdn = data.get("Msisdn")
        shortcode = data.get("Shortcode")
        response_message = data.get("Response")
        payload = {
            "Msisdn": msisdn,
            "Shortcode": shortcode,
            "Response": response_message,
        }

        tasks.process_interactive_shortcode.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(payload,),
        )

        return Response(status=HTTP_200_OK)


class SMSLogReportViewSet(CacheableBaseView):
    """SMSLogReport ViewSet."""

    permissions = {
        "GET": [perms.SMS_VIEW],
        "POST": [],
        "PATCH": [],
        "DELETE": [],
    }
    scopes = {
        "GET": [scopes.SMS_READ],
        "POST": [],
        "PATCH": [],
        "DELETE": [],
    }

    queryset = SMSLogReport.objects.all()
    serializer_class = serializers.SMSLogReportSerializer
