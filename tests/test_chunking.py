import pytest
from app.chunking import chunk_text, fixed_chunks, recursive_chunks


def test_fixed_chunks_overlap():
    chunks = fixed_chunks("abcdefghij", size=5, overlap=2)
    assert chunks == ["abcde", "defgh", "ghij", "j"]


def test_recursive_chunks_limit():
    chunks = recursive_chunks("Hello world. " * 70, size=100, overlap=10)
    assert chunks and all(len(chunk) <= 100 for chunk in chunks)


def test_empty_chunks():
    assert chunk_text("  ", "fixed") == []
    assert chunk_text("  ", "recursive") == []


def test_invalid_strategy():
    with pytest.raises(ValueError):
        chunk_text("hello", "invalid")  # type: ignore[arg-type]


def test_recursive_preserves_long_unbroken_text():
    text = ''.join(chr(0x1000 + i) for i in range(700))
    chunks = recursive_chunks(text, size=100, overlap=15)
    assert all(character in ''.join(chunks) for character in text)
    assert all(len(chunk) <= 100 for chunk in chunks)
