# Preview and activate a natural-language rule

This complete script adds a named policy:

> Block personalized financial recommendations. General financial definitions are allowed.

Laya evaluates **actual sample text** through `POST /api/admin/semantic/preview`.
The rule applies only to model input. Preview does not activate the rule or send
a completion request to your protected model.

Download the [complete examples](../downloads/fastfence-examples.zip) into your installation's `examples/` directory and use the activated FastFence virtual environment. Run commands from the installation directory.

## Prerequisites

Complete [the local gateway setup](protected-request.md#start-the-gateway). Keep
Ollama and FastFence running. This example requires the private management
credential from `state/credentials.json`, or `FASTFENCE_ADMIN_TOKEN` supplied
through your environment. Legacy `security-admin` credentials are also supported.

## Preview first

```sh
python examples/semantic_policy.py
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
python examples/semantic_policy.py --activate
```

This reruns the previews, checks their expected outcomes, refetches the active
policy to reject concurrent changes, then submits the candidate through the actual
`PUT /api/admin/policy` endpoint. The server validates the version and configured
source. A failed preview or conflict stops the example without activation.

Now test the active policy through the normal protected request path:

```sh
python examples/protected_request.py \
  --prompt 'Buy this stock immediately with all your savings.'
python examples/protected_request.py \
  --prompt 'Define a stock as a financial instrument.'
```

Edit the `RULE` and `CASES` constants to explore another policy. Keep a blocked and
a permitted sample with expectations you chose independently. For exact character
restrictions, use a deterministic text rule instead of treating model judgment as
exact matching. Removing the named rule through **Policies** requires another
reviewed policy version.

<!-- source: examples/docs/semantic_policy.py -->
