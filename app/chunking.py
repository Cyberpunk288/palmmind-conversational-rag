from typing import Literal

Strategy = Literal["fixed", "recursive"]


def fixed_chunks(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    """Character-based chunking with overlap."""
    if not 0 <= overlap < size:
        raise ValueError("overlap must be non-negative and smaller than size")
    text = text.strip()
    if not text:
        return []
    step = size - overlap
    return [text[i:i + size] for i in range(0, len(text), step) if text[i:i + size].strip()]


def recursive_chunks(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    """Prefer paragraphs, then lines, sentences and spaces; overlap is applied to result."""
    if not 0 <= overlap < size:
        raise ValueError("overlap must be non-negative and smaller than size")
    separators = ["\n\n", "\n", ". ", " "]

    def split(piece: str, level: int) -> list[str]:
        if len(piece) <= size:
            return [piece] if piece.strip() else []
        if level == len(separators):
            return [piece[i:i + size] for i in range(0, len(piece), size)]
        separator = separators[level]
        parts = piece.split(separator)
        if len(parts) == 1:
            return split(piece, level + 1)
        results: list[str] = []
        current = ""
        for part in parts:
            candidate = current + (separator if current else "") + part
            if len(candidate) <= size:
                current = candidate
            else:
                if current.strip():
                    results.append(current)
                if len(part) > size:
                    results.extend(split(part, level + 1))
                    current = ""
                else:
                    current = part
        if current.strip():
            results.append(current)
        return results

    pieces = split(text.strip(), 0)
    if not pieces:
        return []
    # Reuse trailing context from previous chunk while preserving maximum size.
    output: list[str] = [pieces[0]]
    for piece in pieces[1:]:
        prefix = output[-1][-overlap:] if overlap else ""
        output.append((prefix + piece)[-size:])
    return output


def chunk_text(text: str, strategy: Strategy) -> list[str]:
    if strategy == "fixed":
        return fixed_chunks(text)
    if strategy == "recursive":
        return recursive_chunks(text)
    raise ValueError("Unknown chunking strategy")
