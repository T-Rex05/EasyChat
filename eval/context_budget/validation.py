"""Deterministic factual and formatting checks; no model judge."""
import json
import re


def strict_json(text):
    text = text.strip()
    fenced = re.fullmatch(r"\x60{3}(?:json)?\s*(.*?)\s*\x60{3}", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError:
        return None


def validate_answer(text, expected):
    strict = strict_json(text)
    if strict is not None:
        return {"facts_correct": same_json(strict, expected), "format_correct": True}
    first = re.search(r"[\[{]", text)
    value = None
    if first:
        try:
            value, _ = json.JSONDecoder().raw_decode(text[first.start():])
        except ValueError:
            pass
    return {"facts_correct": same_json(value, expected), "format_correct": False}


def same_json(actual, expected):
    if isinstance(expected, bool):
        return type(actual) is bool and actual == expected
    if isinstance(expected, (int, float)):
        return type(actual) in (int, float) and actual == expected
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            same_json(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            same_json(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected
