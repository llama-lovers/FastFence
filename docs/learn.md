# Learn FastFence

Use these tasks in order on your own local installation. Each task has one observable outcome. The [manual verification guide](manual-testing.md) contains the longer end-to-end checklist.

## Runnable code first

Install the [package](getting-started.md), download its [complete runnable examples](downloads/fastfence-examples.zip), and extract them into your installation's `examples/` directory. Start with the full [REST client](examples/protected-request.md), [named Laya rule](examples/semantic-policy.md), [MCP client](examples/mcp-client.md), or [FastMCP server](examples/fastmcp-server.md). Every page embeds the executable source.

## 1. Send a protected model request

Complete [Getting started](getting-started.md), including the Laya setup and the local assessment and completion models. Open the console, connect your agent and management identities, and choose **Test requests**. Select the model, enter a short prompt and send the request.

The result shows the policy version, decision, reason and whether the upstream model ran. Open its audit link to inspect the same request in **Activity**. A denied input must show that the upstream operation did not run.

The equivalent REST request is:

```sh
curl http://127.0.0.1:8000/api/models/complete \
  -H "Authorization: Bearer $FASTFENCE_AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3:0.6b","prompt":"Hi","max_output_tokens":16}'
```

Set `FASTFENCE_AGENT_TOKEN` to your provisioned agent credential in your own shell. Never commit it or substitute a management credential. Use the model identifier from your active policy if it differs from this example.

## 2. Write a Laya rule and test its meaning

In **Policies**, choose **Add Laya rule**. Give it the ID `no-personal-investment-advice` and enter:

> Block personalized recommendations to buy or sell a specific investment. Allow general explanations of financial concepts.

Choose **Input only** and **Models**. In **Sample content**, enter `Tell me which stock I should buy with my retirement savings.` and select **Test with Laya**. The test calls the actual configured assessment model; it does not send a request to the protected completion model or activate the rule.

Compare with a permitted example such as `Explain what portfolio diversification means.` Test realistic variations and inspect unexpected results. The displayed decision is the combined semantic assessment, including other applicable rules, rather than proof that one named rule matched.

Select **Review policy change**, then **Review changes**. Check the instruction, input/model scope and any provider settings in the diff. Confirm the review and select **Activate policy**. The new version and named rule appear in **Policies**. Use **Test requests** to verify the complete gateway path with the rule active.

Changing the instruction, sample or scope invalidates the earlier test. A timeout or unavailable model does not activate anything. For **Input and output**, the dialog tests input; for **Models and tools**, it tests model content. The result states the tested scope. See [semantic rule configuration](policies.md#named-laya-rules) for testing other scope combinations through the API.

### Exact text rules: the letter-a example

A character restriction belongs in **Add content rule**: choose `Word contains`, value `a`, input direction, model target, and leave case sensitivity off. Test `Hi` and `Cat`, review and activate. `Cat` must then be blocked by the local matcher before model execution; `Hi` can reach the model if the remaining controls permit it.

**Describe a fast rule** is a separate authoring workflow: Laya translates a supported instruction into a bounded configuration proposal. Review its diff and generated regression cases before activation. Its compiled literal rule is different from the meaning-based **Add Laya rule** workflow above.

## 3. Make a configuration change

Use the settings editor in **Policies** for a structured change. Review the difference from the active policy and confirm before publishing. The console displays the new active version after the server accepts the update.

If your policy source is a remote HTTP bundle, edit that authoritative source. The console reports it as read-only. A failed validation or version conflict leaves the active snapshot in place; inspect the error, refresh the active state and review your changes again.

## 4. Protect document content

Complete [OCR setup](getting-started.md), connect an agent identity and open **Documents**. Upload PNG, JPEG or a multipage PDF. Inspect the policy-checked Markdown before sending it to an allowed model.

Anonymization applies through the same policy controls as other input and output. Original restoration is off by default and requires both reversible mode and permission on the relevant rule. OCR extraction does not modify the original document.

## 5. Extend with business tools

The default local runtime contains no simulated business handlers. The repository's [business-tool example](https://github.com/llama-lovers/HackYeah2026-challenge-second/tree/main/examples/business_tools) is a separate runnable application. Use it to learn the tool port and policy contract before connecting your own implementation.

For adapter details, see the [integration reference](integration-reference.md). For source boundaries and extension points, see [architecture](architecture.md).
