"""Billing settings."""

from sil_advantage.settings.manager import SettingManager

ORG_BILLING_SETTINGS = [
    SettingManager(
        "billing:require_approval_for_refunds",
        "Require Approval for Refunds",
        False,
        bool,
        None,
    ),
    SettingManager(
        "billing:require_approval_for_discounts",
        "Require Approval for Discounts",
        False,
        bool,
        None,
    ),
    SettingManager(
        "billing:multiple_billing_points",
        "Do you have multiple billing points? ",
        False,
        bool,
        None,
    ),
]
BRANCH_BILLING_SETTINGS = [
    SettingManager(
        "billing:transactional_sender_id",
        "Transactional Sender ID",
        "BeWellApp",
        str,
        None,
    ),
    SettingManager(
        "billing:promotional_sender_id",
        "Promotional Sender ID",
        "Slade360Adv",
        str,
        None,
    ),
]
