# Canonical result files — MANIFEST

Provider-variance study raw per-call logs (JSONL). Archived from ~/pv_runs/ (which is gitignored).
Repo commit at archive time: `2830d6ac56ba100bc4dcc878bd06e804682ab2f4`

| cell | file | rows | bytes | sha256 |
|------|------|------|-------|--------|
| GSM8K/70B | `gsm8k_llama-3.3-70b/gsm8k.jsonl` |     9900 |  15320200 | `d5c42d17e8ac2755210534f64a28f4fa7b77e7d4face8cf46a9243c1cefb3db4` |
| MMLU/70B | `mmlu_llama-3.3-70b/mmlu.jsonl` |     9000 |  9218807 | `45fbbe07a2786c3df1de6e876aa4678ee4203293e9b6864307d9bf62b571c2e0` |
| MMLU/8B | `mmlu_llama-3.1-8b/mmlu.jsonl` |     6300 |  8029338 | `e8062f795de48b0f6807232df8b53a2dddba25704d03fb6d591e0d468113a5fc` |
| HumanEval/70B(recovered) | `humaneval_llama-3.3-70b_recovered/humaneval.jsonl` |     4920 |  14011661 | `3f1efc75ddbccb49366b78ceaf21e6d9af0041e331d5a891c9b874e8e45f64c1` |
| HumanEval/8B | `humaneval_llama-3.1-8b/humaneval.jsonl` |     3444 |  7226118 | `eae618720c1cd66294142bc6da2d8ebb1efccf54fa31947a3acc8df4f07fcc57` |

Verify after extraction:  `shasum -a 256 -c CHECKSUMS.sha256`
