"""Offline tests for MMLU parser + HumanEval sandbox grader."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.benchmarks import humaneval, mmlu


# ---- MMLU ----------------------------------------------------------------------------
def test_mmlu_letter_parse():
    assert mmlu.parse_answer("A").parsed == "A"
    assert mmlu.parse_answer("The answer is C.").parsed == "C"
    assert mmlu.parse_answer("Answer: B").parsed == "B"
    assert mmlu.parse_answer("blah").parsed is None
    assert mmlu.parse_answer("blah").path == "unparseable"


def test_mmlu_no_letter_inside_word():
    # 'A' inside 'Apple' should not be mistaken for a standalone answer letter
    assert mmlu.parse_answer("Apple is a fruit, so D").parsed == "D"


def test_mmlu_completeness():
    assert mmlu.is_complete("A") is True
    assert mmlu.is_complete("") is False
    assert mmlu.is_complete("no letters here") is False


def test_mmlu_grade_and_prompt():
    item = {"subject": "high_school_math", "question": "2+2=?",
            "choices": ["3", "4", "5", "6"], "answer": 1, "gold": "B"}
    correct, parse = mmlu.grade("B", item["gold"])
    assert correct is True and parse["path"] == "letter"
    dev = [{"question": "1+1=?", "choices": ["1", "2", "3", "4"], "answer": 1}]
    msgs = mmlu.build_prompt(item, dev)
    content = msgs[0]["content"]
    assert content.count("Answer:") == 2          # 1 exemplar + target
    assert content.rstrip().endswith("Answer:")
    assert "high school math" in content


# ---- HumanEval sandbox ---------------------------------------------------------------
_ITEM = {
    "prompt": "def add(a, b):\n    \"\"\"Return a+b.\"\"\"\n",
    "test": "def check(candidate):\n    assert candidate(2, 3) == 5\n    assert candidate(-1, 1) == 0\n",
    "entry_point": "add",
}


def test_humaneval_pass():
    correct, info = humaneval.grade("    return a + b\n", _ITEM)
    assert correct is True
    assert info["exec_status"] == "pass"


def test_humaneval_fail():
    correct, info = humaneval.grade("    return a - b\n", _ITEM)
    assert correct is False
    assert info["exec_status"] == "fail"


def test_humaneval_timeout():
    correct, info = humaneval.grade("    while True:\n        pass\n", _ITEM, timeout_s=2.0)
    assert correct is False
    assert info["exec_status"] == "timeout"


def test_humaneval_sanitizes_fenced_and_extra():
    # fenced code + trailing extra def should be handled
    comp = "```python\n    return a + b\n```\ndef other():\n    pass\n"
    code = humaneval.sanitize_completion(comp, _ITEM["prompt"])
    assert "return a + b" in code
    assert "def other" not in code
