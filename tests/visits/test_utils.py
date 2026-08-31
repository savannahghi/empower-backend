"""Test visits utils generate_document_number."""
from sil_advantage.visits.views import generate_document_number


def test_basic_document_number():
    """Test that the basic document number is generated correctly."""
    setting = "{custom_input}/{org}/{branch}/{year}/{seq}"
    document_number = generate_document_number(
        setting, "XYZ", "Omega Corporation", "North Branch", 2021, "123"
    )
    assert document_number == "XYZ/OME/NOR/2021/0123", "Basic formatting failed"


def test_missing_parts():
    """Test document number is correctly generated even if some parts are missing."""
    setting = "{custom_input}/{org}/{year}/{seq}"
    document_number = generate_document_number(
        setting, "XYZ", "Omega Corporation", "North Branch", 2021, "123"
    )
    assert document_number == "XYZ/OME/2021/0123", "Handling of missing parts failed"


def test_empty_prefix():
    """Test the handling of an empty custom_input in the document number generation."""
    setting = "{custom_input}/{org}/{branch}/{year}/{seq}"
    document_number = generate_document_number(
        setting, "", "Omega Corporation", "North Branch", 2021, "123"
    )
    assert (
        document_number == "/OME/NOR/2021/0123"
    ), "Handling of empty custom_input failed"


def test_numerical_sequence_padding():
    """Ensure that numerical sequences are padded correctly in the document number."""
    setting = "{custom_input}/{org}/{branch}/{year}/{seq}"
    document_number = generate_document_number(
        setting, "XYZ", "Omega Corporation", "North Branch", 2021, "1"
    )
    assert document_number == "XYZ/OME/NOR/2021/0001", "Sequence padding failed"


def test_custom_prefix():
    """Test that custom custom_inputs are handled correctly in the document number."""
    setting = "{buru}/{org}/{branch}/{year}/{seq}"
    document_number = generate_document_number(
        setting, "XYZ", "Omega Corporation", "North Branch", 2021, "1"
    )
    assert document_number == "BURU/OME/NOR/2021/0001", "Custom prefix handling failed"
