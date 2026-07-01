"""HumanEval benchmark: raw function-signature completion + sandboxed unit-test grading.

Prompt (PREREGISTRATION §10.2): raw completion — the model is given the function signature +
docstring and completes the body. NOT instruction-wrapped.
Grading (§10.5, §10.6): extract/sanitize the completion, assemble  prompt + code + official test
+ check(entry_point), and execute in a FRESH subprocess (isolated `-I`), temp cwd, process-group
kill, 10s wall-clock timeout. A candidate PASSES iff the process exits 0.

SECURITY: this executes model-generated code. Isolation is process-level (subprocess + timeout +
killpg + temp dir), no Docker (per §10.6). Do not run untrusted expansions without reviewing.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile


def build_prompt(prompt_text: str) -> list[dict[str, str]]:
    """Raw completion: send the HumanEval prompt as the user message, no instruction wrapper."""
    return [{"role": "user", "content": prompt_text}]


def _strip_fences(c: str) -> str:
    if "```" not in c:
        return c
    seg = c.split("```")
    if len(seg) >= 3:                        # take content of the first fenced block
        block = seg[1]
        if block.lstrip().lower().startswith("python"):
            block = block.split("\n", 1)[1] if "\n" in block else ""
        return block
    return c


def sanitize_completion(completion: str | None, prompt_text: str = "") -> str:
    """Extract just the candidate code from a chat completion.

    Rules that preserve VALID code (incl. indented nested helper defs) while dropping trailing
    junk the model appended:
      * take the first fenced block if present;
      * keep the first non-empty line; if it is a COLUMN-0 `def`/`async def` it's a full-function
        completion and that def line is allowed;
      * truncate at the first LATER column-0 line that begins a new top-level construct
        (def/class/if __name__/print/assert/import/from/comment) — i.e. only unindented foreign
        statements are cut, never the indented body of the target function.
    """
    if not completion:
        return ""
    c = _strip_fences(completion)
    lines = c.split("\n")
    first_idx = next((i for i, l in enumerate(lines) if l.strip()), None)
    if first_idx is None:
        return ""
    kept = []
    for i, l in enumerate(lines):
        if i > first_idx and l[:1] not in ("", " ", "\t"):  # a column-0 line after the start
            if re.match(r"(def |class |async def |if __name__|print\(|assert |import |from |#)", l):
                break
        kept.append(l)
    return "\n".join(kept)


def _is_full_function(code: str) -> bool:
    """True if the code is itself a full function definition (col-0 def as first non-empty line)."""
    for l in code.split("\n"):
        if l.strip():
            return bool(re.match(r"(async )?def ", l))  # unindented def
    return False


def _run_program(program: str, timeout_s: float) -> tuple[str, str]:
    """Run `program` in an isolated subprocess. Returns (status, stderr_snippet).

    status in {'pass','fail','timeout','error'}.
    """
    with tempfile.TemporaryDirectory() as d:
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-c", program],
                cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,  # own process group so we can kill children on timeout
                env={"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"},
            )
        except OSError as e:  # noqa: BLE001
            return "error", repr(e)[:300]
        try:
            _, err = proc.communicate(timeout=timeout_s)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            return "timeout", ""
    if rc == 0:
        return "pass", ""
    return "fail", (err.decode("utf-8", "replace")[:300] if err else "")


def build_program(item: dict, code: str) -> str:
    """Assemble the executable program. If `code` is a full function (col-0 def), use it
    standalone; otherwise it's a body continuation and we prepend the prompt signature."""
    body_or_full = code if _is_full_function(code) else (item["prompt"] + code)
    return (
        body_or_full + "\n\n"
        + item["test"] + "\n\n"
        + f"check({item['entry_point']})\n"
    )


def is_complete(text: str | None) -> bool:
    """No reliable text-level completeness signal for code; defer to finish_reason/tests.

    Returning True disables silent-truncation flagging for HumanEval (a truncated body simply
    fails its unit test; finish=='length' is handled separately as an our-cap exclusion).
    """
    return True


def grade(completion: str | None, item: dict, timeout_s: float = 10.0) -> tuple[bool, dict]:
    code = sanitize_completion(completion, item["prompt"])
    program = build_program(item, code)
    status, err = _run_program(program, timeout_s)
    return (status == "pass"), {"exec_status": status, "stderr": err,
                                "code_chars": len(code)}
