# Bilingual user-supplied prompt corpus

`training_prompts.jsonl` preserves the 400 exact prompt strings from the user-provided
`prompty_treningowe.json` (3 October 2026), with original sample IDs and source
indices, label, language, family and generator/classifier names. The source SHA-256
is `91fdaddbc611f52638eafbec23c18c4949952cef68801676e7d13ed1e37480ad`.
The normalized JSONL SHA-256 is
`e4fe2f4ccb09adb245a1094a5d218abe50e58a04236fd99eb56578c991abc7fb`.
Discarded-generation metadata and verbose classifier explanations are excluded.

There are 200 `good_prompt` and 200 `bad_prompt` entries, with 100 Polish and
100 English entries per label. Both generation and labelling metadata name Qwen.
These are synthetic development labels, **not independently human-adjudicated
ground truth or a held-out security certification**. No original labels were
changed to agree with the implementation. Six email examples use reserved
`example.com`/`example.org` domains; no apparent credential material was found.

Unit tests validate all entries and exercise real deterministic literal matching,
scope isolation and email redaction. Literal policies deliberately cannot
distinguish quoted attacks from instructions. An unmatched attack is not considered
safe: semantic assessment is a separate stage. Tests never stub the classifier
to return an expected label and never claim a passing unit suite measures LLM
accuracy.

Run from the contributor checkout:

```sh
uv run pytest --no-cov -q tests/unit/test_training_prompt_corpus.py
uv run python -m evaluation.run_training_prompts --output evaluation/results/training-prompts-laya.json
```

The second command requires the actual installed Laya environment and a running
Qwen3:4b service. It runs all 400 cases sequentially without changing policy or
calling the business model. It records scores, errors and a confusion matrix
overall and by language. Prompt text and credentials are not copied into the
report. A mismatch or unavailable assessment causes a nonzero exit **after the
report is saved**. It also reports the deterministic signature-only baseline;
this is not a whole-gateway acceptance test or benchmark of combined decisions.

## First actual run

On 3 October 2026, Laya/Qwen3:4b assessed all 400 prompts in 342.2 seconds of
summed assessment time with no provider errors. Against the supplied synthetic
labels: 186 true positives, 187 true negatives, **14 missed attacks and 13 false
positives** (93.25% accuracy, 93% recall). Polish recall was 90%; English recall
was 96%. All false positives came from `quoted_attack` or `untrusted_text`
families. The report retains every disagreement; no labels were changed.

The deterministic signature-only baseline was 9 true positives, 194 true
negatives, 191 false negatives and 6 false positives. That feed is a narrow
literal layer, not a substitute for semantic classification. These two
measurements are separate component results, not combined gateway accuracy.
