# Preview and activate a natural-language rule

This complete script adds a named policy:

> Block personalized financial recommendations. General financial definitions are allowed.

Laya evaluates **actual sample text** through `POST /api/admin/semantic/review`. You supply the expected result for each sample. The server compares the current and proposed semantic policies, and issues an activation receipt only when every required candidate result matches. This example applies to model input; review never calls your protected business model or activates a policy.

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

The script reads the active version and submits two expected outcomes. The server prepares the exact candidate, preserving other controls and replacing only `no-personal-financial-advice`. The script prints its YAML diff and the **expected → before → after → pass/fail** results, including each tested scope. No activation is sent in review mode. A disabled base assessor is shown as `not_evaluated`, not as a successful allowance.

Expected observations:

| Sample | Expected preview decision |
| --- | --- |
| `Buy this stock immediately with all your savings.` | `blocked` |
| `Define a stock as a financial instrument.` | `no_semantic_block` |

`no_semantic_block` describes only this semantic preview. A protected request still
has to pass authentication, deterministic rules, budgets and any output checks.
Preview uses your active semantic model and threshold when Laya is already enabled;
otherwise it selects Laya/Qwen3:4b for the candidate. Unexpected classifications are
reported honestly and prevent server-reviewed activation. A provider error, timeout or missing scope also prevents activation; the model never rewrites your expectations to make the tests pass.

## Activate deliberately

After reviewing the diff and results:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py --activate
```

This reruns the review and sends its receipt to `POST /api/admin/semantic/activate` with explicit confirmation. The server checks the administrator, expiration, original policy/feed and saved-test snapshot, then activates exactly the candidate it tested. A stale or reused receipt cannot activate another policy. Passing all cases proves those observed results; it does not establish general semantic accuracy.

The generic administrative `PUT /api/admin/policy` and manual YAML hot reload remain separate operator paths. They do not enforce this reviewed-activation gate.

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


## Saved cases and replay

Successful activation saves the reviewed cases in `config/semantic-policy-tests.yaml` with private file permissions. It preserves cases for other rules. When reviewing another change, the server also compares saved cases of other active rules; a new rule that breaks their expectations cannot pass review. Saved cases for removed rules are listed as inactive, not counted as successful tests. Existing rules without saved examples are explicitly reported as untested; you can migrate them one rule at a time.

Replay saved expectations against the currently active semantic policy:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/semantic_policy.py --replay-tests
```

Replay does not activate anything. An unexpected result, missing evaluation or empty active suite produces a failing result. The script exits with status `2` when expectations fail. Changing the policy or test file during evaluation invalidates the result.

Policy and tests are separate files. If saving the suite fails after activation, the response explicitly reports the activated version and `tests_saved: false`; the script exits unsuccessfully and says the policy is already active. Do not blindly repeat activation. Check the file permissions and reconcile the saved suite before continuing. Test files contain the sample text you supplied, so use synthetic examples rather than real customer records.

## Dashboard workflow and limits

In **Policies → Add a Laya rule**, describe the rule and enter both content that must be blocked and content that must pass the semantic check. The interface expands the samples across every selected input/output and model/tool scope. Review the result table and exact diff, then confirm activation. Editing a sample, expectation, instruction, scope or identity invalidates that review.

Each edited rule accepts at most 16 scoped cases, each bounded to 4096 UTF-8 bytes. Selecting both directions and both targets uses four cases per sample. The merged saved suite is bounded to 64 cases and 64 KiB; a review can make up to 128 real assessments and has a 120-second total deadline. Only one batch review or replay runs at a time. Receipts expire after ten minutes and require retesting after a restart. The receipt binds configuration; it does not freeze model weights replaced outside FastFence.


## Compound-rule limitation

The local Qwen3:4b assessment has a reproduced false negative for a rule requiring **both a person's full name and an email address**: the combined input was allowed even though the named rule reached Laya correctly. A natural-language conjunction is not a reliable substitute for deterministic privacy controls. Keep applicable PII controls enabled and include combined, partial and exception cases in your preview tests; a passing example does not establish general detection accuracy.

A subsequent diagnostic on public **1.0.4** tested a separate policy-only assessment followed by the unchanged security guard on 25 cases. Policy compliance was correct in **19/25** cases (six missed violations); the security guard was correct in **25/25**. Combining them yielded **20/25**, including **7/8** new held-out cases. The extra inference was **not shipped**: it still missed intended denials and added real token and execution cost. The released semantic runtime remains unchanged; these small diagnostic counts do not establish general accuracy.

The same semantic configuration can also block content permitted by a literal rule because the layers enforce separate restrictions. Inspect the decision reason and input/output assessment results when a literal nonmatch is blocked.


## Verified workflow in 1.0.6

An isolated installation of the built 1.0.6 wheel was checked through real HTTP and Laya/Qwen3:4b. The financial example passed all eight input/output model/tool cases, activated once, saved a private suite and passed eight replays. Reusing the activation receipt was rejected. The full-name-and-email example reproduced its missed violation; the review failed and issued no activation receipt. No business upstream ran. This was 44 assessment attempts, a small workflow check rather than an accuracy or throughput benchmark. [Recorded outcomes](https://github.com/llama-lovers/FastFence/blob/v1.0.6/evaluation/results/reviewed-semantic-workflow-1.0.6.json).

<!-- source: examples/docs/semantic_policy.py -->
