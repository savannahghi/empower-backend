"""A central collection of helper utilities for use in this project."""
import random
from decimal import Decimal
from random import randint
from typing import Any, Optional

import phonenumbers
import pyshorteners
from django.conf import settings
from django.db.models import QuerySet
from rest_framework.response import Response


def round_off_decimal(
    value: Decimal,
    decimal_places: int,
) -> Decimal:
    """Round off a decimal value to specified decimal places."""
    decimal_places_str = "1.{}".format("0" * decimal_places)
    value = Decimal(value)
    return value.quantize(Decimal(decimal_places_str))


def round_off_monetary_value(amount: Decimal) -> Decimal:
    """Round off monetary value to decimal places in set in settings."""
    return round_off_decimal(Decimal(amount), settings.DECIMAL_PLACES)


def paginate_response(  # type: ignore
    instance, queryset: QuerySet, serializer: Any = None
) -> Response:
    """Get a paginated response given a queryset and current instance."""
    page = instance.paginate_queryset(queryset)
    serializer = serializer(page, many=True)
    return instance.get_paginated_response(serializer.data)


def format_phone_number_prefix(phone_number: str) -> Optional[str]:
    """Render a phone number in E.164 format."""
    formatted_phone_number = None
    try:
        parsed_number = phonenumbers.parse(phone_number, "KE")
        is_valid = phonenumbers.is_valid_number(parsed_number)
        if is_valid:
            formatted_phone_number = phonenumbers.format_number(
                parsed_number, phonenumbers.PhoneNumberFormat.E164
            )
    except phonenumbers.NumberParseException:
        pass
    return formatted_phone_number


def generate_token(length: int) -> str:
    """Generate a token."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    base = len(alphabet)

    token = ""
    r = randint(0, base**length)
    while r:
        r, digit = divmod(r, base)
        token += alphabet[digit]

    remainder = max(length - len(token), 0)
    token = token + alphabet[0] * remainder
    return token[::-1]


def shorten_url(url: str) -> str:
    """Shorten a URL using TinyUrl."""
    url_shortener = pyshorteners.Shortener()
    shortened_url = url_shortener.tinyurl.short(url)
    return shortened_url


def generate_otp() -> str:
    """Generate a six digit OTP."""
    otp = "".join([str(random.randint(0, 9)) for _ in range(6)])
    return otp
