from __future__ import annotations

import pytest

from hedge_fund.secrets.provider import SecretProvider, SecretProviderError


def test_resolves_op_reference_without_exposing_reference_or_value():
    def runner(args, **kwargs):
        return "secret-value"

    provider = SecretProvider(runner=runner)

    assert provider.resolve("SAXO_APP_SECRET_REF", "op://vault/item/secret") == "secret-value"


def test_missing_reference_names_variable_only():
    def runner(args, **kwargs):
        raise RuntimeError("op failure with supersecret")

    provider = SecretProvider(runner=runner)

    with pytest.raises(SecretProviderError) as error:
        provider.resolve("SAXO_REFRESH_TOKEN_REF", "op://vault/item/token")

    assert "SAXO_REFRESH_TOKEN_REF" in str(error.value)
    assert "op://vault/item/token" not in str(error.value)
    assert "supersecret" not in str(error.value)


def test_write_back_edits_json_template_without_secret_in_arguments_and_rereads():
    import json

    calls = []
    item = {
        "id": "item-id",
        "fields": [
            {"id": "username", "type": "STRING", "label": "username", "value": "alice"},
            {"id": "token", "type": "CONCEALED", "label": "token", "value": "old-token"},
        ],
    }

    def runner(args, **kwargs):
        calls.append((list(args), dict(kwargs)))
        if args[:2] == ["op", "read"]:
            return type("Result", (), {"stdout": item["fields"][1]["value"]})()
        if args[:3] == ["op", "item", "get"]:
            return type("Result", (), {"stdout": json.dumps(item)})()
        if args[:3] == ["op", "item", "edit"]:
            item.update(json.loads(kwargs["input"]))
            return type("Result", (), {"stdout": ""})()
        raise AssertionError(f"unexpected op command: {args}")

    provider = SecretProvider(runner=runner)
    provider.write_back("SAXO_REFRESH_TOKEN_REF", "op://vault/item/token", "rotated-token")

    edit_args, edit_kwargs = calls[-1]
    assert edit_args == ["op", "item", "edit", "item", "--vault", "vault"]
    assert "rotated-token" not in edit_args
    assert json.loads(edit_kwargs["input"])["fields"][1]["value"] == "rotated-token"
    assert provider.resolve("SAXO_REFRESH_TOKEN_REF", "op://vault/item/token") == "rotated-token"


def test_write_back_failure_is_sanitized():
    def runner(args, **kwargs):
        raise RuntimeError("secret echoed")

    provider = SecretProvider(runner=runner)
    with pytest.raises(SecretProviderError) as error:
        provider.write_back("SAXO_REFRESH_TOKEN_REF", "op://vault/item/token", "rotated")
    assert "secret echoed" not in str(error.value)


@pytest.mark.parametrize("section,field", [("sim", "REFRESH-TOKEN"), ("section-sim", "field-sim")])
def test_write_back_honors_section_qualified_references(section, field):
    import json

    item = {
        "fields": [
            {"id": "field-sim", "label": "refresh-token", "section": {"id": "section-sim", "label": "SIM"}, "value": "old"},
            {"id": "field-other", "label": "refresh-token", "section": {"id": "section-other", "label": "Other"}, "value": "other"},
        ]
    }

    def runner(args, **kwargs):
        if args[:3] == ["op", "item", "get"]:
            return json.dumps(item)
        if args[:3] == ["op", "item", "edit"]:
            item.update(json.loads(kwargs["input"]))
            return ""
        raise AssertionError(f"unexpected op command: {args}")

    provider = SecretProvider(runner=runner)
    provider.write_back("SAXO_REFRESH_TOKEN_REF", f"op://vault/item/{section}/{field}", "rotated")

    assert item["fields"][0]["value"] == "rotated"
    assert item["fields"][1]["value"] == "other"


def test_write_back_does_not_fall_back_to_a_field_in_another_section():
    import json

    item = {"fields": [{"id": "token", "label": "token", "section": {"id": "other", "label": "Other"}, "value": "old"}]}
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return json.dumps(item)

    provider = SecretProvider(runner=runner)
    with pytest.raises(SecretProviderError, match="cannot persist"):
        provider.write_back("SAXO_REFRESH_TOKEN_REF", "op://vault/item/SIM/token", "rotated")
    assert len(calls) == 1
