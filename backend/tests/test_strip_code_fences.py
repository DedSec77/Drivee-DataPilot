from __future__ import annotations

from app.api.datasource import _strip_code_fences


def test_strips_yaml_fence():
    raw = "```yaml\nkey: value\n```"
    assert _strip_code_fences(raw) == "key: value"


def test_strips_yml_fence():
    raw = "```yml\nkey: value\n```"
    assert _strip_code_fences(raw) == "key: value"


def test_strips_unlabelled_fence():
    raw = "```\nkey: value\n```"
    assert _strip_code_fences(raw) == "key: value"


def test_no_fence_passes_through():
    raw = "key: value\nother: 1"
    assert _strip_code_fences(raw) == raw


def test_handles_surrounding_whitespace():
    raw = "\n  ```yaml\nkey: value\n```  \n"
    assert _strip_code_fences(raw) == "key: value"


def test_partial_fence_passes_through():
    raw = "```yaml\nkey: value"
    assert _strip_code_fences(raw) == raw
