"""Deterministic caption feature extraction.

Single source of truth: used by the ETL (history), the seed simulator and the
Pre-Publish Lab (drafts), so a draft is featurised exactly like history was.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆✅]")
_HASHTAG = re.compile(r"(?<!\w)#\w+")
_CTA = re.compile(
    r"\b(comment|share this|save this|save it|follow|subscribe|join us|sign up|click|link in bio|"
    r"dm us|tell us|reply|try it|download|book a|register|tag a|let us know|drop a)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TextFeatures:
    caption_length: int
    word_count: int
    hashtag_count: int
    emoji_count: int
    has_cta: bool
    has_question: bool


def extract_text_features(caption: str) -> TextFeatures:
    text = caption or ""
    return TextFeatures(
        caption_length=len(text.strip()),
        word_count=len(text.split()),
        hashtag_count=len(_HASHTAG.findall(text)),
        emoji_count=len(_EMOJI.findall(text)),
        has_cta=bool(_CTA.search(text)),
        has_question="?" in text,
    )


def daypart(hour: int) -> str:
    if 5 <= hour < 11:
        return "Morning"
    if 11 <= hour < 15:
        return "Midday"
    if 15 <= hour < 19:
        return "Afternoon"
    return "Evening"
