"""Forbidden word check for campaign text (biz name, product, keywords)."""
from ..db import query


def load(channel=None):
    return query("SELECT word, channel, severity FROM forbidden_words WHERE channel IS NULL OR channel = %s", [channel])


def check(texts, channel=None):
    """Return {'block': [words], 'warn': [words]} found in any of `texts`."""
    hay = " ".join(t for t in texts if t).lower()
    found = {"block": [], "warn": []}
    for row in load(channel):
        w = row["word"].lower()
        if w and w in hay and row["word"] not in found[row["severity"]]:
            found[row["severity"]].append(row["word"])
    return found
