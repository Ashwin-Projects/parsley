"""[N4] Conservative, deterministic rewrite suggestions for rejected English.

Supported destination templates come from patterns.PATTERNS. Recovery recognizes a
simple store-value-in-name phrasing, or a misspelled first command word. Proposals
are ranked by token overlap and normalized Levenshtein distance, and checked by the
candidate generator. This module never accepts input or produces MiniLang.
"""

from __future__ import annotations

import re

from parsley.keywords import is_reserved
from parsley.nlp import patterns
from parsley.nlp.candidates import generate
from parsley.nlp.normalizer import normalize

_STORE = re.compile(
    r'store\s+(?P<value>-?[0-9]+(?:\.[0-9]+)?|"[^"\n]*")\s+in\s+'
    r'(?P<name>[A-Za-z][A-Za-z0-9_]*)', re.IGNORECASE,
)
_WORDS = re.compile(r'[A-Za-z0-9_]+')


def _distance(left: str, right: str) -> int:
    """Levenshtein distance using one row of memory."""
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        next_row = [i]
        for j, b in enumerate(right, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = next_row
    return row[-1]


def _similarity(left: str, right: str) -> float:
    a, b = left.lower(), right.lower()
    left_words, right_words = set(_WORDS.findall(a)), set(_WORDS.findall(b))
    union = left_words | right_words
    overlap = len(left_words & right_words) / len(union) if union else 0.0
    edit = 1 - _distance(a, b) / max(len(a), len(b), 1)
    return 0.5 * overlap + 0.5 * edit


def _supported(text: str) -> bool:
    result = generate(text)
    # An alternative set is not a single suggested meaning.
    return result.status != 'unsupported' and len(result.candidates) == 1


def _quote(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _split(text: str) -> tuple[str, str] | None:
    """The two supported statements joined by an unquoted ``and``, or None."""
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        return None
    norm = normalize(text)
    for token in norm.tokens:
        if token.kind != 'word' or token.lower != patterns.CONTINUATION_WORD:
            continue
        first, second = norm.text[:token.start].strip(), norm.text[token.end:].strip()
        if first and second and _supported(first) and _supported(second):
            return first, second
    return None


def split_guidance(text: str) -> str | None:
    """How to split a sentence rejected for ``and`` (LANGUAGE_SPEC.md 8); the pipeline
    adds it to the E101 message. None when there are not two supported statements.
    """
    halves = _split(text)
    if halves is None:
        return None
    first, second = halves
    return (
        f'Blocks hold one statement. Try: {_quote(first)} and then '
        f'{_quote(second)} as separate sentences.'
    )


def suggest(text: str, reason_code: str) -> str | None:
    """Return one supported phrasing to try, or None when no safe rewrite is close.

    ``reason_code`` is the primary NLP reason (ARCHITECTURE.md 2.10). For an ``and``
    rejection it is the first statement; ``split_guidance`` explains the split. Malformed,
    excessive, or internal-error inputs receive no speculative rewrite.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        return None
    if reason_code == 'REJECT_AND_CONTINUATION':
        halves = _split(text)
        return halves[0] if halves else None
    if reason_code != 'NO_MATCH':
        return None
    norm = normalize(text)
    if norm.malformed or not norm.tokens:
        return None
    proposals: list[tuple[float, str]] = []
    stored = _STORE.fullmatch(norm.text)
    if stored and not is_reserved(stored['name']):
        assignment = next((p for p in patterns.PATTERNS if p.rule_id == 'S1'), None)
        if assignment:
            rewrite = assignment.template.replace('[', '').replace(']', '')
            rewrite = re.sub(
                r'\b(NAME|VALUE)\b',
                lambda match: stored['name'] if match[0] == 'NAME' else stored['value'],
                rewrite,
            )
            if _supported(rewrite):
                proposals.append((_similarity(norm.text, rewrite), rewrite))

    first = norm.tokens[0]
    if first.kind == 'word':
        for pattern in patterns.PATTERNS:
            head = re.match(r'\(([^)]+)\)|([a-z]+)', pattern.template)
            if head is None:
                continue
            for verb in (head[1] or head[2]).split('|'):
                distance = _distance(first.lower, verb)
                if not 0 < distance <= 2 or distance / max(len(verb), len(first.lower)) > 0.4:
                    continue
                rewrite = verb + norm.text[first.end:]
                if _supported(rewrite):
                    score = 0.8 * _similarity(norm.text, rewrite)
                    score += 0.2 * _similarity(norm.text, pattern.template + ' ' + pattern.example)
                    proposals.append((score, rewrite))
    if not proposals:
        return None
    # Stable pattern-table order breaks ties, so suggestions reproduce across runs.
    return max(proposals, key=lambda item: item[0])[1]
