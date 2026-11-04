from app.execution.assertions import evaluate_assertions
from app.modules.ai.mock_provider import MockGenerationProvider


def test_missing_field_is_not_null() -> None:
    results = evaluate_assertions(
        [{"type": "jsonType", "path": "name", "expected": "string"}],
        status_code=200,
        body_text='{"id": "p-1"}',
    )
    assert results[0]["errorClass"] == "missing_field"
    null_result = evaluate_assertions(
        [{"type": "jsonType", "path": "name", "expected": "string"}],
        status_code=200,
        body_text='{"name": null}',
    )
    assert null_result[0]["errorClass"] == "null_value"


def test_equals_does_not_coerce_string_and_number() -> None:
    result = evaluate_assertions(
        [{"type": "equals", "path": "price", "expected": 1}],
        status_code=200,
        body_text='{"price": "1"}',
    )
    assert result[0]["passed"] is False
    assert result[0]["errorClass"] == "strict_mismatch"
    integer_ok = evaluate_assertions(
        [{"type": "equals", "path": "price", "expected": 1}],
        status_code=200,
        body_text='{"price": 1}',
    )
    assert integer_ok[0]["passed"] is True


def test_integer_and_number_are_distinct() -> None:
    result = evaluate_assertions(
        [{"type": "jsonType", "path": "price", "expected": "integer"}],
        status_code=200,
        body_text='{"price": 1.5}',
    )
    assert result[0]["errorClass"] == "type_mismatch"
    assert result[0]["actual"] == "number"


def test_range_rejects_numeric_string() -> None:
    result = evaluate_assertions(
        [{"type": "range", "path": "price", "minimum": 0, "maximum": 10}],
        status_code=200,
        body_text='{"price": "5"}',
    )
    assert result[0]["errorClass"] == "type_mismatch"
    inside = evaluate_assertions(
        [{"type": "range", "path": "price", "minimum": 0, "maximum": 10}],
        status_code=200,
        body_text='{"price": 5}',
    )
    assert inside[0]["passed"] is True


def test_non_json_body() -> None:
    result = evaluate_assertions(
        [{"type": "jsonType", "path": "name", "expected": "string"}],
        status_code=200,
        body_text="not-json",
    )
    assert result[0]["errorClass"] == "non_json"


def test_mock_does_not_invent_401_without_contract() -> None:
    cases = MockGenerationProvider().generate(
        project_name="演示",
        contract={
            "method": "GET",
            "path": "/api/products",
            "requiresAuth": False,
            "responses": {"200": {"type": "object", "properties": {"items": {"type": "array"}}}},
        },
    )
    expected = [item.get("expected") for case in cases for item in case["assertions"]]
    assert 401 not in expected
    assert cases[0]["assertions"]
    assert cases[0]["origin"] == "mock"


def test_mock_adds_401_only_when_contract_declares_it() -> None:
    denied = MockGenerationProvider().generate(
        project_name="演示",
        contract={"method": "GET", "path": "/secure", "requiresAuth": True, "responses": {"200": {}, "401": {}}},
    )
    allowed = [item.get("expected") for case in denied for item in case["assertions"]]
    assert 401 in allowed
    silent = MockGenerationProvider().generate(
        project_name="演示",
        contract={"method": "GET", "path": "/secure", "requiresAuth": True, "responses": {"200": {}}},
    )
    silent_expected = [item.get("expected") for case in silent for item in case["assertions"]]
    assert 401 not in silent_expected
