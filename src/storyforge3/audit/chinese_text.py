from __future__ import annotations

import re
from collections import Counter


def count_chinese_chars(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")


def split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n|[\r\n]+", text) if part.strip()]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", text)
    return [part.strip() for part in parts if part.strip()]


def density(text: str, words: tuple[str, ...]) -> float:
    chars = max(count_chinese_chars(text), 1)
    hits = sum(text.count(word) for word in words)
    return hits * 1000 / chars


def regex_count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text))


def repeated_phrases(text: str, *, length: int = 5, min_count: int = 4) -> list[tuple[str, int]]:
    chars = "".join(char for char in text if "\u4e00" <= char <= "\u9fff")
    counter = Counter(chars[index : index + length] for index in range(max(0, len(chars) - length + 1)))
    return [(phrase, count) for phrase, count in counter.items() if count >= min_count]


def has_unbalanced_pairs(text: str) -> bool:
    pairs = [("“", "”"), ("《", "》"), ("（", "）"), ("(", ")"), ("[", "]")]
    return any(text.count(left) != text.count(right) for left, right in pairs)


def sentence_ratio(sentences: list[str], words: tuple[str, ...]) -> float:
    if not sentences:
        return 0.0
    hits = sum(1 for sentence in sentences if any(word in sentence for word in words))
    return hits / len(sentences)


def max_quiet_paragraph_run(paragraphs: list[str], markers: tuple[str, ...]) -> int:
    longest = current = 0
    for paragraph in paragraphs:
        if any(marker in paragraph for marker in markers):
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest
