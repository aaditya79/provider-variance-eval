"""GSM8K benchmark: frozen 8-shot CoT prompt + locked exact-match grader.

Pre-registered (PREREGISTRATION §10.2, §10.5):
  * Prompt: standard 8-shot chain-of-thought using the Wei et al. exemplars, each ending
    with a `#### <answer>` delimiter. The 8 exemplars are FROZEN here and copied into the
    item file at freeze time so the exact prompt is reproducible.
  * Grading: take the number after `####`; else fall back to the LAST number in the text;
    normalize commas / `$` / trailing `.0`. The parse path is recorded for every call.

The prompt template is byte-identical across all providers and models (paired design).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Frozen 8-shot CoT exemplars (Wei et al., 2022), adapted to the #### delimiter --------
# Do NOT edit without a pre-registration amendment commit; these are part of the frozen prompt.
GSM8K_8SHOT_EXEMPLARS: list[dict[str, str]] = [
    {
        "question": "There are 15 trees in the grove. Grove workers will plant trees in the "
        "grove today. After they are done, there will be 21 trees. How many trees did the "
        "grove workers plant today?",
        "answer": "There are 15 trees originally. Then there were 21 trees after some more "
        "were planted. So there must have been 21 - 15 = 6.\n#### 6",
    },
    {
        "question": "If there are 3 cars in the parking lot and 2 more cars arrive, how many "
        "cars are in the parking lot?",
        "answer": "There are originally 3 cars. 2 more cars arrive. 3 + 2 = 5.\n#### 5",
    },
    {
        "question": "Leah had 32 chocolates and her sister had 42. If they ate 35, how many "
        "pieces do they have left in total?",
        "answer": "Originally, Leah had 32 chocolates. Her sister had 42. So in total they "
        "had 32 + 42 = 74. After eating 35, they had 74 - 35 = 39.\n#### 39",
    },
    {
        "question": "Jason had 20 lollipops. He gave Denny some lollipops. Now Jason has 12 "
        "lollipops. How many lollipops did Jason give to Denny?",
        "answer": "Jason started with 20 lollipops. Then he had 12 after giving some to "
        "Denny. So he gave Denny 20 - 12 = 8.\n#### 8",
    },
    {
        "question": "Shawn has five toys. For Christmas, he got two toys each from his mom and "
        "dad. How many toys does he have now?",
        "answer": "Shawn started with 5 toys. If he got 2 toys each from his mom and dad, "
        "then that is 4 more toys. 5 + 4 = 9.\n#### 9",
    },
    {
        "question": "There were nine computers in the server room. Five more computers were "
        "installed each day, from monday to thursday. How many computers are now in the "
        "server room?",
        "answer": "There were originally 9 computers. For each of 4 days, 5 more computers "
        "were added. So 5 * 4 = 20 computers were added. 9 + 20 = 29.\n#### 29",
    },
    {
        "question": "Michael had 58 golf balls. On tuesday, he lost 23 golf balls. On "
        "wednesday, he lost 2 more. How many golf balls did he have at the end of wednesday?",
        "answer": "Michael started with 58 golf balls. After losing 23 on tuesday, he had "
        "58 - 23 = 35. After losing 2 more, he had 35 - 2 = 33 golf balls.\n#### 33",
    },
    {
        "question": "Olivia has $23. She bought five bagels for $3 each. How much money does "
        "she have left?",
        "answer": "Olivia had 23 dollars. 5 bagels for 3 dollars each will be 5 x 3 = 15 "
        "dollars. So she has 23 - 15 = 8 dollars left.\n#### 8",
    },
]

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


@dataclass
class ParseResult:
    """Outcome of parsing a model completion (logged for every call)."""

    parsed: str | None       # normalized numeric string, or None if nothing parseable
    path: str                # "delimiter" | "last_number" | "unparseable"
    raw_match: str | None    # the exact substring matched, pre-normalization


def normalize_number(s: str) -> str:
    """Normalize a numeric string: strip $, commas, whitespace, and a trailing '.0'."""
    s = s.strip().replace(",", "").replace("$", "")
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".")[0]
    # also strip a trailing dot, e.g. "8." -> "8"
    s = s.rstrip(".")
    return s


def parse_answer(text: str | None) -> ParseResult:
    """GSM8K parser with FLAGGED fallback (PREREGISTRATION §17).

    Paths:
      * 'delimiter'                  -> '####' present with a number after it (intended path).
      * 'delimiter_missing_flagged'  -> no '####' at all; last-number fallback used, FLAGGED.
      * 'delimiter_unusable_flagged' -> '####' present but no number after it; fallback, FLAGGED.
      * 'unparseable'                -> no number anywhere.
    The last-number fallback still yields a gradeable value, but is NEVER silent: any non-
    'delimiter' path is flagged so format-deviating completions can be audited by hand.
    """
    if not text:
        return ParseResult(None, "unparseable", None)
    has_delim = "####" in text
    if has_delim:
        after = text.split("####")[-1]
        m = _NUM_RE.search(after)
        if m:
            return ParseResult(normalize_number(m.group()), "delimiter", m.group())
    # No usable delimiter answer -> last-number fallback, FLAGGED by which case we hit.
    matches = _NUM_RE.findall(text)
    if matches:
        path = "delimiter_unusable_flagged" if has_delim else "delimiter_missing_flagged"
        return ParseResult(normalize_number(matches[-1]), path, matches[-1])
    return ParseResult(None, "unparseable", None)


def gold_answer(raw_gold: str) -> str:
    """Extract the gold final answer from a GSM8K answer field (always has '#### N')."""
    return normalize_number(raw_gold.split("####")[-1])


def build_prompt(question: str, exemplars: list[dict[str, str]]) -> list[dict[str, str]]:
    """Build the frozen 8-shot CoT chat prompt for one question.

    Single user message containing the 8 exemplars then the target question, instructing
    the model to end with the #### delimiter. No system prompt (PREREGISTRATION §10.2).
    """
    parts = [
        "Solve the math word problem. Show your reasoning, then give the final answer on a "
        "new line in the form '#### <number>'.\n"
    ]
    for ex in exemplars:
        parts.append(f"Question: {ex['question']}\nAnswer: {ex['answer']}\n")
    parts.append(f"Question: {question}\nAnswer:")
    return [{"role": "user", "content": "\n".join(parts)}]


def grade(completion: str | None, raw_gold: str) -> tuple[bool, ParseResult]:
    """Return (is_correct, parse_result). Exact match on normalized numeric strings."""
    pr = parse_answer(completion)
    gold = gold_answer(raw_gold)
    correct = pr.parsed is not None and pr.parsed == gold
    return correct, pr
