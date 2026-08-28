"""Number comma separator."""
from decimal import Decimal

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


def num_comma_separator(value: int | float | Decimal) -> str:
    """Convert value into a comma separated string with 2 float numbers."""
    value = round(float(value), 2)
    return "%s%s" % (intcomma(int(value)), ("%0.2f" % value)[-3:])


register.filter("num_comma_separator", num_comma_separator)
