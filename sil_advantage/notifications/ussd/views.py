"""USSD views."""
from typing import Any, Dict

from requests import Request
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from sil_advantage.notifications.ussd.handlers.registration_handler import (
    RegistrationHandler,
)
from sil_advantage.notifications.ussd.managers.session_manager import (
    SessionManager,
)
from sil_advantage.notifications.ussd.state import MESSAGES, STATE_DEFINITIONS
from sil_advantage.notifications.ussd.state.ussd_statemachine import (
    USSDStateMachine,
)
from sil_advantage.notifications.ussd.validators.custom_validator import (
    CustomValidator,
)


@api_view(["POST"])  # type: ignore
@permission_classes([AllowAny])
@throttle_classes([])
def ussd_view(request: Request) -> Response:
    """View to handle USSD requests and responses."""
    payload: Dict[str, Any] = request.data
    user_input: str = payload["data"]["response"]
    ussd_code: str = payload["data"]["code"]
    phone_number: str = payload["data"]["msisdn"]
    session_id: str = payload["data"]["guid"]

    state_machine = USSDStateMachine(STATE_DEFINITIONS, MESSAGES)  # type: ignore
    session_manager = SessionManager()
    validator = CustomValidator(MESSAGES)
    ussd_handler = RegistrationHandler(state_machine, session_manager, validator)

    response = ussd_handler.handle_request(
        session_id, user_input, phone_number, ussd_code
    )
    return Response({"data": {"detail": response["message"]}})
