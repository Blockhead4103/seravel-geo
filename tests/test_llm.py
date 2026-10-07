import pytest

from geo.llm import LLMError, parse_json_block


def test_plain_json():
    assert parse_json_block('{"a": 1}') == {"a": 1}


def test_fenced_json():
    text = 'Hier das Ergebnis:\n```json\n{"a": [1, 2]}\n```\nDanke.'
    assert parse_json_block(text) == {"a": [1, 2]}


def test_fenced_without_lang():
    text = "```\n{\"x\": true}\n```"
    assert parse_json_block(text) == {"x": True}


def test_json_with_surrounding_prose():
    text = 'Antwort: {"name": "Kevin", "n": 3} -- fertig.'
    assert parse_json_block(text) == {"name": "Kevin", "n": 3}


def test_array_extraction():
    text = 'Liste: [1, 2, 3]'
    assert parse_json_block(text) == [1, 2, 3]


def test_braces_inside_strings():
    text = '{"q": "use {curly} braces", "ok": 1}'
    assert parse_json_block(text) == {"q": "use {curly} braces", "ok": 1}


def test_invalid_raises():
    with pytest.raises(LLMError):
        parse_json_block("kein json hier")


def test_none_raises():
    with pytest.raises(LLMError):
        parse_json_block(None)
