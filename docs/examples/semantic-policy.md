# Preview and activate a natural-language rule

This complete script adds a named policy:

> Block personalized financial recommendations. General financial definitions are allowed.

Laya evaluates **actual sample text** through `POST /api/admin/semantic/preview`.
The rule applies only to model input. Preview does not activate the rule or send
a completion request to your protected model.

Download the [complete examples](../downloads/fastfence-examples.zip) into your installation's `examples/` directory. Run commands from the installation directory; `uv run` supplies Python 3.12 and the FastFence package for each example, without activating a virtual environment.

## Prerequisites

Complete [the local gateway setup](protected-request.md#start-the-gateway). Keep
Ollama and FastFence running. This example requires the private management
credential from `state/credentials.json`, or `FASTFENCE_ADMIN_TOKEN` supplied
through your environment. Legacy `security-admin` credentials are also supported.

## Preview first

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py
```

The script fetches the active policy, preserves its other controls, adds or replaces
only `no-personal-financial-advice`, and increments the candidate version. It asks
the real preview endpoint to classify two samples, then prints their actual results
and a YAML diff. No `PUT` is sent in preview mode.

Expected observations:

| Sample | Expected preview decision |
| --- | --- |
| `Buy this stock immediately with all your savings.` | `blocked` |
| `Define a stock as a financial instrument.` | `no_semantic_block` |

`no_semantic_block` describes only this semantic preview. A protected request still
has to pass authentication, deterministic rules, budgets and any output checks.
Preview uses your active semantic model and threshold when Laya is already enabled;
otherwise it selects Laya/Qwen3:4b for the candidate. Unexpected classifications are
reported honestly and prevent this script's activation step.

## Activate deliberately

After reviewing the diff and results:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py --activate
```

This reruns the previews, checks their expected outcomes, refetches the active
policy to reject concurrent changes, then submits the candidate through the actual
`PUT /api/admin/policy` endpoint. The server validates the version and configured
source. A failed preview or conflict stops the example without activation.

Now test the active policy through the normal protected request path:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/protected_request.py \
  --prompt 'Buy this stock immediately with all your savings.'
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/protected_request.py \
  --prompt 'Define a stock as a financial instrument.'
```

Edit the `RULE` and `CASES` constants to explore another policy. Keep a blocked and
a permitted sample with expectations you chose independently. For exact character
restrictions, use a deterministic text rule instead of treating model judgment as
exact matching. Removing the named rule through **Policies** requires another
reviewed policy version.


## Compound-rule limitation

The local Qwen3:4b assessment has a reproduced false negative for a rule requiring **both a person's full name and an email address**: the combined input was allowed even though the named rule reached Laya correctly. A natural-language conjunction is not a reliable substitute for deterministic privacy controls. Keep applicable PII controls enabled and include combined, partial and exception cases in your preview tests; a passing example does not establish general detection accuracy.

The same semantic configuration can also block content permitted by a literal rule because the layers enforce separate restrictions. Inspect the decision reason and input/output assessment results when a literal nonmatch is blocked.

<!-- source: examples/docs/semantic_policy.py -->
