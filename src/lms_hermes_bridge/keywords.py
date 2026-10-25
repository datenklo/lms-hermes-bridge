"""Keyword matching shared by the Hermes router and the routines table."""
import re
from functools import lru_cache

# Spaces inside a keyword phrase tolerate a filler article: "create file" matches "create a file".
_GAP = r"\s+(?:(?:a|an|the|my|ein|eine|einen|einem|der|die|das|den|dem|mein|meine|meinen)\s+)?"


@lru_cache(maxsize=32)
def compile_keywords(keywords: tuple[str, ...]) -> re.Pattern | None:
    """Whole-word match; a trailing * on a keyword also matches longer forms (install* -> installing)."""
    parts = []
    for kw in keywords:
        kw = kw.strip()
        if not kw.strip("*"):
            continue
        words = []
        for word in kw.split():
            prefix = word.endswith("*")
            words.append(re.escape(word.rstrip("*")) + (r"\w*" if prefix else r"(?!\w)"))
        parts.append(_GAP.join(words))
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + ")", re.I) if parts else None


def find(prompt: str, keywords) -> re.Match | None:
    rx = compile_keywords(tuple(keywords))
    return rx.search(prompt) if rx else None
