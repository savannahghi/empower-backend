"""Patient app utilities."""
import logging
import tempfile
from datetime import date, datetime, timedelta
from typing import Any, Dict

import dateparser
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.common.models.common_models import Attachment
from sil_advantage.common.utilities.misc import format_phone_number_prefix

LOGGER = logging.getLogger(__name__)


def upload_patient_records(  # type: ignore  # import cycle issue
    headers: list,
    patients: list[tuple],
    resolved_mappings: Dict[str, int],
    patient_list_upload,
) -> list[Dict[Any, Any]]:
    """Upload patients extracted from a patient list file."""
    # Import's here due to circular dependency issues
    from sil_advantage.patients.models import Patient

    uploaded_persons = []
    failed_uploads = []
    success_count = 0
    fail_count = 0

    common_fields = {
        "organisation": patient_list_upload.organisation,
        "created_by": patient_list_upload.created_by,
        "updated_by": patient_list_upload.updated_by,
        "workstation_id": patient_list_upload.workstation_id,
        "department_id": patient_list_upload.department_id,
        "cluster_id": patient_list_upload.cluster_id,
        "branch_id": patient_list_upload.branch_id,
    }
    for patient in patients:
        patient_record = list(
            map(lambda x: x if x is not None else "", patient)  # stringify None values
        )
        try:
            patient_data = get_patient_data(resolved_mappings, patient_record)
        except Exception as e:
            patient_record.append(str(e))
            failed_uploads.append(tuple(patient_record))
            fail_count += 1
            continue

        # check if person already exists
        person_exists_qs = Person.objects.filter(
            first_name=patient_data.get("first_name"),
            last_name=patient_data.get("last_name"),
            person_contacts__contact__in=patient_data.get("phone_number"),
            organisation=patient_list_upload.organisation,
        )

        if person_exists_qs.exists():
            patient_record.append("Person with matching details already exists.")
            failed_uploads.append(tuple(patient_record))
            fail_count += 1

            uploaded_person = {
                "person": person_exists_qs.first(),
                "extras": patient_data.get("extras"),
            }
            uploaded_persons.append(uploaded_person)
            continue

        person_obj = Person(
            first_name=patient_data.get("first_name"),  # type: ignore
            last_name=patient_data.get("last_name"),  # type: ignore
            other_names=patient_data.get("other_name"),
            date_of_birth=patient_data.get("date_of_birth"),
            gender=patient_data.get("gender"),
            title=None,
            **common_fields,
        )
        contacts = []
        for i, phone_number in enumerate(patient_data.get("phone_number")):  # type: ignore
            contact_obj = PersonContact(
                person=person_obj,
                contact=phone_number,
                contact_type="phone_number",
                is_primary_contact=(i == 0),
                **common_fields,
            )
            contacts.append(contact_obj)
        patient_obj = Patient(person=person_obj, source="UPLOAD", **common_fields)

        try:
            with transaction.atomic():
                person_obj.save()
                for contact in contacts:
                    contact.save()
                patient_obj.save()
                success_count += 1
                uploaded_person = {
                    "person": person_obj,
                    "extras": patient_data.get("extras"),
                }
                uploaded_persons.append(uploaded_person)
        except ValidationError as e:
            patient_record.append(str(e))
            failed_uploads.append(tuple(patient_record))
            fail_count += 1
    if failed_uploads:
        generate_failed_records_excel(headers, failed_uploads, patient_list_upload)

    patient_list_upload.success_count = success_count
    patient_list_upload.fail_count = fail_count
    patient_list_upload.process_state = "COMPLETE"
    patient_list_upload.save()

    return uploaded_persons


def get_patient_data(resolved_mappings: Dict[str, int], record: list) -> Dict[str, Any]:
    """Get patient data from a single record.

    patient_data sample format:
        {
            "first_name": Jane,
            "last_name": Doe,
            "phone_number": +254746103674,
            "extras": {
                "clinic_name": "Nairobi",
                "tca_date": "12/5/2024",
            }
        }
    """
    now = timezone.now()
    patient_data = {}
    extra_data = {}

    for field, index in resolved_mappings.items():
        match field:
            case "first_name":
                patient_data["first_name"] = record[index].title()
            case "last_name":
                patient_data["last_name"] = record[index].title()
            case "other_names":
                patient_data["other_name"] = record[index].title()
            case "full_name":
                name = record[index].split()
                name.insert(1, "")

                patient_data["first_name"] = name[0].title()
                patient_data["last_name"] = name[-1].title()
                patient_data["other_name"] = (
                    " ".join(name[1:-1]).title().strip() or None
                )
            case "phone_number":
                parsed_numbers_list = []
                phone_number_list = str(record[index]).strip().split("/")
                for phone_number in phone_number_list:
                    parsed_number = format_phone_number_prefix(phone_number)
                    if parsed_number:
                        parsed_numbers_list.append(parsed_number)

                patient_data["phone_number"] = parsed_numbers_list

            case "gender":
                gender = record[index].strip().upper()
                if gender not in (
                    "MALE",
                    "FEMALE",
                ):
                    gender = "OTHER"
                patient_data["gender"] = gender
            case "age":
                # extract the patient's age,
                # Note that this uses a best effort approach
                # and defaults to a 01/01/1980 DOB
                try:
                    age = int(record[index])
                except ValueError:
                    patient_data["date_of_birth"] = date(1980, 1, 1)
                    continue

                days = (age * 365) + age // 4  # adds an extra day for leap years
                date_of_birth = now - timedelta(days=days)
                patient_data["date_of_birth"] = date_of_birth
            case "date_of_birth":
                dob = record[index]
                if not isinstance(dob, datetime):
                    dob = dateparser.parse(dob.strip())
                patient_data["date_of_birth"] = dob
            case _:  # pragma: no cover
                extra_data_value = record[index]
                if isinstance(extra_data_value, datetime):
                    extra_data_value = extra_data_value.strftime("%B %d, %Y")

                extra_data[field] = extra_data_value
                msg = "No match found"
                LOGGER.warning(msg)
    if extra_data:
        patient_data["extras"] = extra_data

    return patient_data


def generate_failed_records_excel(  # type: ignore  # import cycle issue
    headers: list, failed_uploads: list, patient_list_upload
) -> None:
    """Generate a file with patients that failed to upload."""
    work_book = Workbook()
    work_sheet = work_book.active
    work_sheet.title = "Failed Patient Records"

    work_sheet.append(headers)

    for record in failed_uploads:
        work_sheet.append(record)

    common_fields = {
        "organisation": patient_list_upload.organisation,
        "created_by": patient_list_upload.created_by,
        "updated_by": patient_list_upload.updated_by,
        "workstation_id": patient_list_upload.workstation_id,
        "department_id": patient_list_upload.department_id,
        "branch_id": patient_list_upload.branch_id,
        "cluster_id": patient_list_upload.cluster_id,
    }

    file_name = "Failed_Patient_Records.xlsx"
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmpfile:
        work_book.save(filename=tmpfile.name)
        file_obj = File(tmpfile)

        attachment = Attachment.objects.create(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            data=file_obj,
            title=file_name,
            size=file_obj.size,
            **common_fields,
        )

        patient_list_upload.failed_uploads_file = attachment
        patient_list_upload.save()
