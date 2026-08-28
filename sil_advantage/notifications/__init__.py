"""Notifications app."""


GROUP_ROLES = [
    ("DAILY_DIGEST", "DAILY_DIGEST"),
]

USSD_GATEWAYS = [
    ("SAFARICOM", "SAFARICOM"),
]

USSD_CODE_TYPE = [
    # Session cost covered by end user
    ("PREPAID", "Pre-Paid USSD Code"),
    # Session cost covered by service code owner
    ("POSTPAID", "Post-Paid USSD Code"),
]
