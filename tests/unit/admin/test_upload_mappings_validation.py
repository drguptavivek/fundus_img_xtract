from admin.upload_mappings import _validate_mydriatic_flags


def test_validate_mydriatic_flags_rejects_no_allowed_scope():
    assert _validate_mydriatic_flags(
        allow_mydriatic=False,
        allow_non_mydriatic=False,
        default_is_mydriatic=False,
    ) == "Select at least one mydriatic scope."


def test_validate_mydriatic_flags_rejects_mydriatic_default_when_disallowed():
    assert _validate_mydriatic_flags(
        allow_mydriatic=False,
        allow_non_mydriatic=True,
        default_is_mydriatic=True,
    ) == "Default cannot be mydriatic unless mydriatic uploads are allowed."


def test_validate_mydriatic_flags_rejects_non_mydriatic_default_when_disallowed():
    assert _validate_mydriatic_flags(
        allow_mydriatic=True,
        allow_non_mydriatic=False,
        default_is_mydriatic=False,
    ) == "Default cannot be non-mydriatic unless non-mydriatic uploads are allowed."


def test_validate_mydriatic_flags_accepts_valid_combinations():
    assert _validate_mydriatic_flags(
        allow_mydriatic=True,
        allow_non_mydriatic=False,
        default_is_mydriatic=True,
    ) is None
