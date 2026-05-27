"""Tests for promoter name normalization."""

from __future__ import annotations

import pytest

from db.promoter_normalizer import normalize


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ABC Builders Pvt Ltd", "abc builders"),
        ("ABC Builders Private Limited", "abc builders"),
        ("abc  builders", "abc builders"),
        ("  Foo Developers Ltd.  ", "foo"),
        ("Bar & Sons LLP", "bar sons"),
        ("Baz Corp.", "baz"),
        ("Quux Co.", "quux"),
        ("HERO Group", "hero"),
        ("", ""),
        ("   ", ""),
        # Non-suffix words are preserved
        ("Acme Towers", "acme towers"),
        # Mixed punctuation
        ("M/s. Acme, Inc.", "m s acme"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_normalize_idempotent() -> None:
    first = normalize("ABC Builders Pvt Ltd")
    assert normalize(first) == first
