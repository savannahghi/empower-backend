"""Custom model fields."""
from typing import Any

import orjson
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models


class EncryptedJsonField(models.TextField):
    """Field that stores encrypted JSON values."""

    def get_db_prep_save(
        self,
        value: Any,
        connection: Any,
    ) -> Any:
        """Encrypt the field's value before for saving into the DB."""
        value = super().get_db_prep_save(value, connection)
        if value is None:
            return value

        fernet = Fernet(settings.INTEGRATION_CONFIG_ENCRYPTION_KEY)
        json_string = orjson.dumps(value)
        return fernet.encrypt(json_string).decode()

    def to_python(self, value: Any) -> Any:
        """Convert the value to a Python object."""
        if value is None or not isinstance(value, str):
            return value

        fernet = Fernet(settings.INTEGRATION_CONFIG_ENCRYPTION_KEY)
        raw = fernet.decrypt(value.encode("utf-8")).decode()
        return orjson.loads(raw)

    def from_db_value(
        self,
        value: Any,
        expression: Any,
        connection: Any,
    ) -> Any:
        """Decrypt the value read from the DB."""
        return self.to_python(value)
