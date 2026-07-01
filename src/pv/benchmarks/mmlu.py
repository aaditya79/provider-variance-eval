"""MMLU benchmark: 5-shot letter-match (PREREGISTRATION §10.2, §10.5).

Prompt: standard 5-shot using the SUBJECT's own dev-set exemplars (canonical MMLU protocol),
options labeled A-D, instruction to answer with the single letter. No system prompt.
Grading: first standalone A-D letter; unparseable => incorrect AND flagged.
Identical prompt/parser across all providers and models (paired design).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LETTERS = ["A", "B", "C", "D"]
# First standalone A-D (not embedded in a word).
_LETTER_RE = re.compile(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])")


@dataclass
class ParseResult:
    parsed: str | None      # 'A'..'D' or None
    path: str               # 'letter' | 'unparseable'
    raw_match: str | None


def _fmt_q(question: str, choices: list[str]) -> str:
    lines = [question]
    for letter, choice in zip(LETTERS, choices):
        lines.append(f"{letter}. {choice}")
    return "\n".join(lines)


def build_prompt(item: dict, dev_exemplars: list[dict]) -> list[dict[str, str]]:
    """5-shot chat prompt using the subject's dev exemplars, then the target question."""
    subject = item["subject"].replace("_", " ")
    parts = [f"The following are multiple choice questions (with answers) about {subject}. "
             "Answer with the single letter (A, B, C, or D).\n"]
    for ex in dev_exemplars:
        parts.append(f"{_fmt_q(ex['question'], ex['choices'])}\nAnswer: {LETTERS[ex['answer']]}\n")
    parts.append(f"{_fmt_q(item['question'], item['choices'])}\nAnswer:")
    return [{"role": "user", "content": "\n".join(parts)}]


def parse_answer(text: str | None) -> ParseResult:
    if not text:
        return ParseResult(None, "unparseable", None)
    m = _LETTER_RE.search(text)
    if m:
        return ParseResult(m.group(1), "letter", m.group(1))
    return ParseResult(None, "unparseable", None)


def is_complete(text: str | None) -> bool:
    """Complete iff a letter answer was emitted (else finish=stop w/o answer => silent trunc)."""
    return parse_answer(text).parsed is not None


def gold_letter(answer_index: int) -> str:
    return LETTERS[answer_index]


def grade(completion: str | None, gold: str) -> tuple[bool, dict]:
    pr = parse_answer(completion)
    correct = pr.parsed is not None and pr.parsed == gold
    return correct, {"parsed": pr.parsed, "path": pr.path, "raw_match": pr.raw_match}
