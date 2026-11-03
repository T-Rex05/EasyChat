import importlib


def validate(text, expected):
    return importlib.import_module("eval.context_budget.validation").validate_answer(text, expected)


def test_fact_accuracy_and_format_are_reported_separately():
    answer = '\x60\x60\x60json\n{"count":42}\n\x60\x60\x60\nI verified this.'
    result = validate(answer, {"count": 42})
    assert result["facts_correct"] is True
    assert result["format_correct"] is False


def test_exact_json_or_single_fenced_json_is_valid():
    assert validate('{"count":42}', {"count": 42}) == {"facts_correct": True, "format_correct": True}
    assert validate('\x60\x60\x60json\n{"count":42}\n\x60\x60\x60', {"count": 42})["format_correct"]


def test_wrong_first_object_and_missing_values_are_not_rescued_by_answer_search():
    assert not validate('{"count":0} then {"count":42}', {"count":42})["facts_correct"]
    assert not validate('no evidence', {"count":42})["facts_correct"]


def test_boolean_receipt_cannot_be_replaced_with_numeric_zero():
    assert not validate('{"committed":0}', {"committed":False})["facts_correct"]
