# Expanded bilingual development corpus: 1,312 prompts

`training_prompts_expanded.jsonl` preserves every exact prompt, sample ID, source
index, supplied good/bad label, language, family and Qwen generator/labeler from
`prompty_treningowe (1).json`, supplied on 4 October 2026. The source SHA-256 is
`545d02c705194f18802a60c64c586666e8ade5bcc18949058755d56a52ece8a7`.
The normalized fixture is 1,270,152 bytes, SHA-256
`c395b9b7f09f964b62c324fee04f9bae764e589648c6d8f75a335cb05d3be425`.
The companion manifest records provenance, balance and overlap.

There are 656 `good_prompt` and 656 `bad_prompt` cases. Each label contains 328
Polish and 328 English prompts; each original length bucket contains 164 cases
per label. All 1,312 IDs and texts are unique. There are no contradictory labels.
The first 200 cases per label preserve the earlier 400-prompt fixture exactly,
including metadata: this expansion adds **912** cases, not 1,312 independent new
cases. Discarded-generation metadata and verbose classifier explanations are not
included, following the original normalization contract.

These are synthetic, Qwen-generated and Qwen-labelled **development data**. They
are not independently human-adjudicated truth or a blind holdout. Supplied labels
were not changed to fit the implementation. Specific credential detectors found
no credential material or PEM keys; entropy-only detections in prose and sample
IDs are not evidence of real secrets. Email examples are synthetic; two attack
samples additionally name `security-example.org` and `external-hacker.com`, so not
every example domain is an IANA-reserved domain. No addresses are contacted.

The original `training_prompts.jsonl` and its measured
`evaluation/results/training-prompts-laya.json` remain unchanged. That earlier
400-case report **does not measure this 1,312-case expansion**. No new semantic
accuracy result is claimed by ingesting the fixture or passing unit tests.

## Deterministic regressions

```sh
uv run pytest --no-cov -q tests/unit/test_training_prompt_corpus.py tests/unit/test_expanded_training_prompt_corpus.py
```

Tests validate the full fixture and exact original overlap, prove input/output
and model/tool scope boundaries on selected new literal cases, and exercise email
redaction on both supplied labels. Benign quoted overrides still match an explicit
literal ban; semantic intent is a separate decision. No mocked classifier is
made to echo the expected labels. Corpus ingestion remains bounded to two MiB;
request-path limits are unchanged.

## Separate actual Laya evaluation

The existing evaluator accepts the expanded fixture explicitly:

```sh
uv run python -m evaluation.run_training_prompts \
  --corpus tests/test_data/training_prompts_expanded.jsonl \
  --output evaluation/results/training-prompts-expanded-laya.json
```

This requires the installed Laya environment and running Qwen3:4b. It runs all
1,312 semantic assessments sequentially, records the exact corpus digest, actual
scores/errors and confusion matrices, and saves a distinct report. It does not
execute the protected completion model or modify policy. Nonzero exit means an
assessment error or disagreement with the supplied labels after saving results.
The signature-only baseline remains a separate component measurement. Do not
combine this overlapping corpus with the original 400-case score as independent
observations.
