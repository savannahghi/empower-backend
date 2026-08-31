"""Segments Views."""
import uuid
from dataclasses import asdict
from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from jinja2 import Environment
from openpyxl import Workbook
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import UpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from sil_transitions import TransitionViewMixin

from sil_advantage.common.models import Attachment
from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.common.views.base import BaseView, CacheableBaseView
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.notifications.sms.utils import can_send_sms
from sil_advantage.patients.models import Patient, PatientListUpload
from sil_advantage.patients.serializers import PatientListUploadSerializer
from sil_advantage.patients.tasks import process_patient_list_upload
from sil_advantage.permissions import perms, scopes
from sil_advantage.segments import serializers, tasks
from sil_advantage.segments.filters import (
    FilterGroupFilterFilter,
    FilterGroupFilterset,
    JourneyAttributeFilter,
    JourneyFilter,
    JourneyMemberFilter,
    JourneySegmentFilter,
    MessageTemplateFilter,
    MessageTemplateTransitionLogFilter,
    SegmentFilter,
    SegmentMemberFilter,
    SegmentMemberTransitionLog,
    SegmentMemberTransitionLogFilter,
    SegmentMessageDeliveryFilter,
    SegmentMessageFilter,
    SegmentTransitionLogFilter,
    SegmentUploadFilter,
)
from sil_advantage.segments.models import (
    MESSAGE_TEMPLATE_STATUS_TRANSITION_GRAPH,
    SEGMENT_MEMBER_STATUS_TRANSITION_GRAPH,
    SEGMENT_STATUS_TRANSITION_GRAPH,
    Filter,
    FilterChoiceSource,
    FilterGroup,
    FilterGroupFilter,
    Journey,
    JourneyAttributes,
    JourneyMember,
    JourneySegment,
    MessageTemplate,
    MessageTemplateCategories,
    MessageTemplateTransitionLog,
    MessageTemplateType,
    Segment,
    SegmentLabels,
    SegmentMember,
    SegmentMessage,
    SegmentMessageDelivery,
    SegmentMessageDeliveryType,
    SegmentMessageStatus,
    SegmentUpload,
    generate_context_data,
    get_extra_template_variables,
    template_variable_constants,
)
from sil_advantage.segments.models.segments import SegmentTransitionLog
from sil_advantage.sil_auth.models import SILUser

jinja_env = Environment()


class SegmentViewSet(CacheableBaseView):
    """Segment viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = Segment.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.SegmentSerializer
    search_fields = ["name"]

    filterset_class = SegmentFilter

    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[IsAuthenticated],
    )
    def clinical(self, request: AuthenticatedRequest) -> Response:
        """Callback to add a member to a segment from Clinical service."""
        serializer = serializers.SegmentMemberInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.data

        try:
            patient = Patient.objects.get(clinical_id=payload["clinical_id"])
        except ObjectDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        label = SegmentLabels(payload["segment_label"])

        admin_email = settings.SYSTEM_ADMIN_EMAIL
        system_admin = SILUser.objects.get(email=admin_email).id
        segment, _ = Segment.objects.get_or_create(
            label=label,
            defaults={
                "name": label.label,
                "status": "ACTIVE",
                "created_by": system_admin,
                "updated_by": system_admin,
                "organisation": patient.organisation,
            },
        )

        patient_segment_member, _ = SegmentMember.objects.get_or_create(
            organisation=patient.organisation,
            person=patient.person,
            segment=segment,
            defaults={
                "status": "CONFIRMED",
                "created_by": system_admin,
                "updated_by": system_admin,
            },
        )

        data = serializers.SegmentMemberSerializer(patient_segment_member).data

        return Response(data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated],
    )
    def upload(
        self,
        request: AuthenticatedRequest,
        pk: uuid.UUID,
    ) -> Response:
        """Upload patients to a particular segment."""
        user = request.user
        data = request.data
        file = request.FILES["file"]
        request.data.pop("file")

        mapping = {}
        for field, column_header in data.items():
            mapping[field] = column_header

        workstation_id = request.META.get("HTTP_X_WORKSTATION") or request.META.get(
            "X-Workstation"
        )
        department_id = request.META.get("HTTP_X_DEPARTMENT") or request.META.get(
            "X-Department"
        )
        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")
        cluster_id = request.META.get("HTTP_X_CLUSTER") or request.META.get("X-Cluster")

        common_fields = {
            "organisation": user.organisation,
            "cluster_id": cluster_id,
            "branch_id": branch_id,
            "department_id": department_id,
            "workstation_id": workstation_id,
            "created_by": user.guid,
            "updated_by": user.guid,
        }
        attachment = Attachment.objects.create(
            content_type=file.content_type,
            data=file,
            title=file.name,
            size=file.size,
            **common_fields,
        )

        patient_list_upload = PatientListUpload.objects.create(
            mapping=mapping,
            upload_type="SEGMENT",
            upload_file=attachment,
            process_state="IN_PROGRESS",
            **common_fields,
        )

        segment_upload = SegmentUpload.objects.create(
            segment_id=pk, file_upload=patient_list_upload, **common_fields
        )

        process_patient_list_upload.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(patient_list_upload.id,),
            kwargs={"segment_upload_id": segment_upload.id},
        )

        return Response(
            PatientListUploadSerializer(patient_list_upload).data,
            status=status.HTTP_202_ACCEPTED,
        )


class MessageTemplateViewSet(BaseView):
    """MessageTemplate viewset."""

    permissions = {
        "GET": [perms.MESSAGE_TEMPLATE_VIEW],
        "POST": [perms.MESSAGE_TEMPLATE_CREATE],
        "PATCH": [perms.MESSAGE_TEMPLATE_EDIT],
        "DELETE": [perms.MESSAGE_TEMPLATE_DELETE],
    }
    scopes = {
        "GET": [scopes.MESSAGE_TEMPLATE_READ],
        "POST": [scopes.MESSAGE_TEMPLATE_WRITE],
        "PATCH": [scopes.MESSAGE_TEMPLATE_WRITE],
        "DELETE": [scopes.MESSAGE_TEMPLATE_WRITE],
    }

    queryset = MessageTemplate.objects.filter(parent__isnull=True).all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.MessageTemplateSerializer
    search_fields = ["name"]

    filterset_class = MessageTemplateFilter

    def get_object(self) -> MessageTemplate:
        """Override queryset used in get_object."""
        queryset = self.filter_queryset(MessageTemplate.objects.all())

        filter_kwargs = {self.lookup_field: self.kwargs[self.lookup_field]}
        obj: MessageTemplate = get_object_or_404(queryset, **filter_kwargs)

        self.check_object_permissions(self.request, obj)

        return obj

    @action(detail=False, methods=["GET"], url_path=r"(?P<pk>[0-9a-f-]+)/templates")
    def templates(self, request: AuthenticatedRequest, pk: uuid.UUID) -> Response:
        """Fetches all sequence templates."""
        template = get_object_or_404(MessageTemplate, pk=pk)

        queryset = self.filter_queryset(
            template.descendants(include_self=True).with_tree_fields()
        )

        page = self.paginate_queryset(queryset)

        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(
        detail=True,
        methods=["POST"],
    )
    def add_sequenced_message(
        self, request: AuthenticatedRequest, pk: uuid.UUID
    ) -> Response:
        """Adds a new message template to a sequence."""
        template = self.get_object()

        if template.has_sequence:
            latest_template = template.descendants().last()
            request.data["parent"] = latest_template.id
        else:
            request.data["parent"] = template.id

        serializer = serializers.MessageTemplateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["GET"])
    def variables(self, request: AuthenticatedRequest) -> Response:
        """Returns available template variables."""
        segment_ids = request.query_params.getlist("segment_id")

        variables = template_variable_constants()

        extra_variables = get_extra_template_variables(segment_ids)
        if extra_variables:
            for extra_variable in extra_variables:
                variables.append(extra_variable)

        return Response(
            data=[asdict(var) for var in variables], status=status.HTTP_200_OK
        )


class SegmentMessageViewSet(CacheableBaseView):
    """SegmentMessage viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = SegmentMessage.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.SegmentMessageSerializer

    filterset_class = SegmentMessageFilter
    search_fields = ["template__name", "template__template"]

    @action(
        detail=False,
        methods=["POST"],
    )
    def check_sms_balance(self, request: AuthenticatedRequest) -> Response:
        """Checks if the wallet has enough balance to send SMS to segments."""
        serializer = serializers.SegmentSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Calculate number of recipients
        segment_ids = data["segment_ids"]
        recipients = SegmentMember.objects.filter(segment_id__in=segment_ids).count()

        if data.get("template_id") is None:
            template_text = data["template"]
        else:
            template = get_object_or_404(MessageTemplate, id=data["template_id"])
            template_text = template.template

        org = request.user.organisation
        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")

        (
            can_send,
            error_message,
            n_parts,
            estimated_cost,
            wallets,
        ) = can_send_sms(
            org=org,
            branch_id=branch_id,
            intention="BROADCAST",
            message=template_text,
            n_recipients=recipients,
        )

        if not can_send:
            return Response(
                {
                    "status": "INSUFFICIENT_BALANCE",
                    "detail": (
                        "Low wallet balance. Please top up your wallet to continue "
                        "sending messages."
                    ),
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": "SUFFICIENT_BALANCE",
                "message": "Sufficient balance available",
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["POST"],
    )
    def preview(self, request: AuthenticatedRequest) -> Response:
        """Returns a preview of a message being sent to a Segment(s)."""
        serializer = serializers.SegmentSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        segment_members = SegmentMember.objects.filter(
            segment_id__in=data["segment_ids"]
        )
        segment_member = segment_members.first()
        recipients_count = segment_members.count()

        context = generate_context_data(segment_member)  # type: ignore

        if data.get("template_id") is None:
            template_text = data["template"]
        else:
            template = get_object_or_404(MessageTemplate, id=data["template_id"])
            template_text = template.template

        jinja_template = jinja_env.from_string(template_text)
        message = jinja_template.render(**context)

        sender_id = data.get("sender_id")
        sender_name: Optional[str] = None
        if sender_id:
            sender = get_object_or_404(SenderID, id=sender_id)
            sender_name = sender.name

        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")

        can_send, _, _, estimated_cost, wallets = can_send_sms(
            org=request.user.organisation,
            branch_id=branch_id,
            intention="BROADCAST",
            message=template_text,
            n_recipients=recipients_count,
        )

        balance_status = "SUFFICIENT_BALANCE" if can_send else "INSUFFICIENT_BALANCE"
        wallet_balance = (
            wallets.get("bulk_sms_account", {}).get("balance", 0) if wallets else 0
        )
        segments = Segment.objects.filter(id__in=data["segment_ids"]).values_list(
            "name", flat=True
        )
        response_data = {
            "status": balance_status,
            "balance": str(wallet_balance),
            "sender": sender_name,
            "recipients": recipients_count,
            "estimated_cost": str(round(estimated_cost or Decimal("0.00"), 2)),
            "segments": ", ".join(segments),
            "message_preview": message,
        }

        return Response(response_data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["POST"],
    )
    def send_sms(self, request: AuthenticatedRequest) -> Response:
        """Sends message to one or more segments at a time.

        Payload format:
            {
                "segment_ids": "[
                    "<guid>",
                    "<guid>",
                ]",
                "sender_id": "<guid>",
                "template_id": "<guid>",
                "template": {
                    "name": "<str>",
                    "template": "<str>",
                    "message_type": "<str>"
                },
                "delivery_type": "<str>",
                "scheduled_at": "<YYYY-MM-DD HH:mm:SS",
                "sequence_interval": "<str>", # crontab string
            }
        """
        serializer = serializers.SegmentSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.data

        if data.get("template_id") is None:
            template_data = {
                "name": MessageTemplateCategories.INSTANT.label,
                "category": MessageTemplateCategories.INSTANT,
                "template": data["template"],
                "message_type": MessageTemplateType.SINGULAR,
            }

            template_serializer = serializers.MessageTemplateSerializer(
                data=template_data, context={"request": request}
            )
            template_serializer.is_valid(raise_exception=True)
            template_serializer.validated_data["status"] = SegmentMessageStatus.ACTIVE
            template_serializer.save()
            template_id = template_serializer.data["id"]
        else:
            template_id = data["template_id"]

        response_data = {"template_id": template_id, "segments": []}

        for segment_id in data["segment_ids"]:
            segment_message_data = {
                "template": template_id,
                "segment": segment_id,
                "sender_id": data["sender_id"],
                "delivery_type": data["delivery_type"],
                "send_on_segment_join": data["send_on_segment_join"],
            }

            if data["delivery_type"] == SegmentMessageDeliveryType.SCHEDULED_ONE_TIME:
                segment_message_data["scheduled_at"] = data["scheduled_at"]
            elif (
                data["delivery_type"] == SegmentMessageDeliveryType.SCHEDULED_RECURRENT
            ):
                segment_message_data["sequence_interval"] = data["sequence_interval"]

            segment_message_serializer = serializers.SegmentMessageSerializer(
                data=segment_message_data, context={"request": request}
            )
            segment_message_serializer.is_valid(raise_exception=True)
            segment_message_serializer.save()

            response_data["segments"].append(
                {
                    "segment_id": segment_id,
                }
            )

        return Response(data=response_data, status=status.HTTP_201_CREATED)


class SegmentMemberViewSet(CacheableBaseView):
    """SegmentMember viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = SegmentMember.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.SegmentMemberSerializer
    search_fields = [
        "person__first_name",
        "person__last_name",
        "person__other_names",
    ]

    filterset_class = SegmentMemberFilter


class SegmentMessageDeliveryViewSet(CacheableBaseView):
    """SegmentMessageDelivery viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = SegmentMessageDelivery.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.SegmentMessageDeliverySerializer
    search_fields = [
        "member__person__first_name",
        "member__person__last_name",
        "member__person__other_names",
    ]

    filterset_class = SegmentMessageDeliveryFilter

    @action(detail=False, methods=["GET"])
    def consolidated_delivery_metrics(
        self,
        request: AuthenticatedRequest,
    ) -> Response:
        """Return a consolidated delivery metric report aggregated by state."""
        try:
            segment_message_id = request.GET["segment_message_id"]
            message_id = request.GET["message_id"]
        except KeyError:
            return Response(
                {"error": "Segment Message ID & Message Template ID must be provided!"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        segment_message_delivery_qs = SegmentMessageDelivery.objects.filter(
            segment_message_id=uuid.UUID(segment_message_id),
            message_template=uuid.UUID(message_id),
        )

        consolidated_report: dict = {}

        data = segment_message_delivery_qs.values(state=F("sms__state")).annotate(
            total=Count("sms__state")
        )
        consolidated_report["count"] = segment_message_delivery_qs.count()
        consolidated_report["data"] = data

        return Response(consolidated_report)

    @action(
        detail=False,
        methods=["POST"],
    )
    def retry_failed_segment_messages(
        self,
        request: AuthenticatedRequest,
    ) -> Response:
        """Retry sending failed messages within a segment message."""
        payload = request.data
        try:
            segment_message_id = payload["segment_message_id"]
            message_id = payload["message_id"]
        except KeyError:
            return Response(
                {"error": "Segment Message ID & Message Template ID must be provided!"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tasks.retry_failed_to_send_segment_messages.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(segment_message_id, message_id),
        )

        return Response(status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["POST"])
    def generate_delivery_metrics_report(
        self,
        request: AuthenticatedRequest,
    ) -> HttpResponse:
        """Generate and return an Excel delivery metrics report."""
        payload = request.data
        try:
            segment_message_id = payload["segment_message_id"]
            message_id = payload["message_id"]
        except KeyError:
            return Response(
                {"error": "Segment Message ID & Message Template ID must be provided!"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        segment_message_delivery_qs = (
            SegmentMessageDelivery.objects.filter(
                segment_message_id=uuid.UUID(segment_message_id),
                message_template=uuid.UUID(message_id),
            )
            .exclude(sms__isnull=True)
            .values(
                "member__person__first_name",
                "member__person__last_name",
                "sms__message",
                "sms__recipients",
                "sms__state",
                "sms__created",
            )
        )
        if not segment_message_delivery_qs:
            error_msg = {
                "detail": "Unable to generate report." "No matching message logs found."
            }
            return Response(
                error_msg,
                status=status.HTTP_400_BAD_REQUEST,
            )

        work_book = Workbook()
        work_sheet = work_book.active
        work_sheet.title = "Segment Message Delivery Report"
        headers = [
            "First Name",
            "Last Name",
            "Message",
            "Phone Number",
            "Status",
            "Delivery Date",
        ]
        work_sheet.append(headers)

        for segment_message in segment_message_delivery_qs.iterator():
            segment_message["sms__recipients"] = segment_message["sms__recipients"][0]
            # format datetime field for readability
            segment_message["sms__created"] = segment_message["sms__created"].strftime(  # type: ignore  # noqa: B950
                "%A %d. %B %Y"
            )
            work_sheet.append(list(segment_message.values()))

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        segment_message_obj = SegmentMessage.objects.get(id=segment_message_id)
        file_name = f"{segment_message_obj.template.name} SMS Delivery Report.xlsx"
        response["Content-Disposition"] = f"attachment; filename={file_name}"
        work_book.save(response)

        return response


class SegmentUploadViewSet(CacheableBaseView):
    """SegmentUpload viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = SegmentUpload.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.SegmentUploadSerializer
    search_fields = ("file_upload__upload_file__title",)

    filterset_class = SegmentUploadFilter


class FilterViewSet(BaseView):
    """Filter viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = Filter.objects.all()
    serializer_class = serializers.FilterSerializer
    search_fields = ["name", "source"]
    filter_backends = [
        DjangoFilterBackend,
    ]

    @action(detail=False, methods=["GET"], url_path=r"(?P<pk>[0-9a-f-]+)/choices")
    def choices(self, request: AuthenticatedRequest, pk: uuid.UUID) -> Response:
        """Fetches choices for a filter."""
        filter = get_object_or_404(Filter, pk=pk)

        match filter.choice_source:
            case FilterChoiceSource.CLOSE_ENDED_CHOICES:
                choices = filter.close_ended_choices
            case _:
                choices = []

        page = self.paginate_queryset(choices)
        serializer = serializers.FilterChoicesSerializer(page, many=True)

        return self.get_paginated_response(serializer.data)


class FilterGroupViewSet(BaseView):
    """FilterGroup viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = FilterGroup.objects.all().prefetch_related("filters__filter")
    serializer_class = serializers.FilterGroupSerializer
    filterset_class = FilterGroupFilterset


class FilterGroupFilterViewSet(BaseView):
    """FilterGroupFilter viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = FilterGroupFilter.objects.all()
    serializer_class = serializers.FilterGroupFilterSerializer
    filterset_class = FilterGroupFilterFilter


class SegmentTransitionLogView(TransitionViewMixin, UpdateAPIView):
    """Segment Transition Log API View."""

    queryset = Segment.objects.all()
    serializer_class = serializers.SegmentSerializer
    lookup_field = "id"

    transition_graph = SEGMENT_STATUS_TRANSITION_GRAPH
    transition_field = "status"
    transition_log_serializer = serializers.SegmentTransitionLogSerializer

    def process_data(
        self,
        data: dict,
        transition_from: str,
        transition_to: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Handle transition data."""
        data["updated_by"] = self.request.user.guid  # type: ignore


class SegmentTransitionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Segment Transition Log API ReadOnly ViewSet."""

    queryset = SegmentTransitionLog.objects.all()
    serializer_class = serializers.SegmentTransitionLogSerializer

    filterset_class = SegmentTransitionLogFilter


class MessageTemplateTransitionLogView(TransitionViewMixin, UpdateAPIView):
    """Segment Transition Log API View."""

    queryset = MessageTemplate.objects.all()
    serializer_class = serializers.MessageTemplateSerializer
    lookup_field = "id"

    transition_graph = MESSAGE_TEMPLATE_STATUS_TRANSITION_GRAPH
    transition_field = "status"
    transition_log_serializer = serializers.MessageTemplateTransitionLogSerializer

    def process_data(
        self,
        data: dict,
        transition_from: str,
        transition_to: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Handle transition data."""
        data["updated_by"] = self.request.user.guid  # type: ignore


class MessageTemplateTransitionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """MessageTemplate Transition Log API ReadOnly ViewSet."""

    queryset = MessageTemplateTransitionLog.objects.all()
    serializer_class = serializers.MessageTemplateTransitionLogSerializer
    filterset_class = MessageTemplateTransitionLogFilter


class SegmentMemberTransitionLogView(TransitionViewMixin, UpdateAPIView):
    """SegmentMember Transition Log API View."""

    queryset = SegmentMember.objects.all()
    serializer_class = serializers.SegmentMemberSerializer
    lookup_field = "id"

    transition_graph = SEGMENT_MEMBER_STATUS_TRANSITION_GRAPH
    transition_field = "status"
    transition_log_serializer = serializers.SegmentMemberTransitionLogSerializer

    def process_data(
        self,
        data: dict,
        transition_from: str,
        transition_to: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Handle transition data."""
        data["updated_by"] = self.request.user.guid  # type: ignore


class SegmentMemberTransitionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """SegmentMember Transition Log API ReadOnly ViewSet."""

    queryset = SegmentMemberTransitionLog.objects.all()
    serializer_class = serializers.SegmentMemberTransitionLogSerializer

    filterset_class = SegmentMemberTransitionLogFilter


class UpdateSegmentFiltersView(APIView):
    """API to trigger the execution of segment filters."""

    def post(self, request: AuthenticatedRequest, segment_id: str) -> Response:
        """Trigger segment filters execution."""
        segment = get_object_or_404(Segment, id=segment_id)

        tasks.execute_segment_filter_cube_query.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(str(segment.id),),
        )
        return Response(
            {"message": "Segment filters update initiated."},
            status=status.HTTP_200_OK,
        )


class JourneyViewSet(CacheableBaseView):
    """Journey viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = Journey.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.JourneySerializer
    search_fields = ["name"]

    filterset_class = JourneyFilter


class JourneySegmentViewSet(CacheableBaseView):
    """Journey Segment viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = JourneySegment.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.JourneySegmentSerializer

    filterset_class = JourneySegmentFilter


class JourneyMemberViewSet(CacheableBaseView):
    """Journey Members viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = JourneyMember.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.JourneyMemberSerializer

    filterset_class = JourneyMemberFilter


class JourneyAttributesViewSet(CacheableBaseView):
    """Journey Attributes viewset."""

    permissions = {
        "GET": [perms.SEGMENT_VIEW],
        "POST": [perms.SEGMENT_CREATE],
        "PATCH": [perms.SEGMENT_EDIT],
        "DELETE": [perms.SEGMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.SEGMENT_READ],
        "POST": [scopes.SEGMENT_WRITE],
        "PATCH": [scopes.SEGMENT_WRITE],
        "DELETE": [scopes.SEGMENT_WRITE],
    }

    queryset = JourneyAttributes.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = serializers.JourneyAttributeSerializer

    filterset_class = JourneyAttributeFilter
