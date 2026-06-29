"""Offline tests for the locked GSM8K parser/grader (PREREGISTRATION §10.5)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.benchmarks import gsm8k


def test_delimiter_path():
    pr = gsm8k.parse_answer("Some reasoning here.\n#### 42")
    assert pr.parsed == "42"
    assert pr.path == "delimiter"


def test_delimiter_takes_last_when_multiple():
    pr = gsm8k.parse_answer("#### 1 then more\nfinal\n#### 7")
    assert pr.parsed == "7"
    assert pr.path == "delimiter"


def test_fallback_last_number():
    pr = gsm8k.parse_answer("The chain says 12 then 13 then finally 18 apples")
    assert pr.parsed == "18"
    assert pr.path == "last_number"


def test_normalization_commas_dollar_trailing_zero():
    assert gsm8k.normalize_number("$1,234.00") == "1234"
    assert gsm8k.normalize_number("8.") == "8"
    assert gsm8k.normalize_number("1,000") == "1000"
    pr = gsm8k.parse_answer("#### $1,234")
    assert pr.parsed == "1234"


def test_unparseable():
    pr = gsm8k.parse_answer("no digits at all here")
    assert pr.parsed is None
    assert pr.path == "unparseable"
    pr2 = gsm8k.parse_answer(None)
    assert pr2.parsed is None


def test_grade_correct_and_incorrect():
    gold_raw = "Reasoning...\n#### 18"
    correct, pr = gsm8k.grade("Long CoT...\n#### 18", gold_raw)
    assert correct is True
    correct2, _ = gsm8k.grade("Long CoT...\n#### 19", gold_raw)
    assert correct2 is False


def test_gold_answer_extraction():
    assert gsm8k.gold_answer("blah blah\n#### 72") == "72"
    assert gsm8k.gold_answer("x\n#### 1,080") == "1080"


def test_prompt_is_8shot_and_ends_with_target():
    msgs = gsm8k.build_prompt("What is 2+2?", gsm8k.GSM8K_8SHOT_EXEMPLARS)
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    content = msgs[0]["content"]
    assert content.count("Question:") == 9  # 8 exemplars + 1 target
    assert content.count("####") == 9       # 8 exemplar answers + 1 in the format instruction
    assert content.rstrip().endswith("Answer:")
