"""House style for any text that reaches a page: no em dashes, including text from ESPN, news and the LLM."""
from __future__ import annotations

import re

_SPACED = re.compile(r"\s*(?:—|\\u2014)\s*")


def no_em_dash(s: str) -> str:
    """'A — B' -> 'A, B'; a bare em dash (empty-value placeholder) -> '-'."""
    s = re.sub(r"(?<=\S)\s+(?:—|\\u2014)\s+(?=\S)", ", ", s)
    return _SPACED.sub("-", s)


def no_em_dash_bytes(b: bytes) -> bytes:
    return no_em_dash(b.decode("utf-8")).encode("utf-8") if (b"\xe2\x80\x94" in b or b"\\u2014" in b) else b
