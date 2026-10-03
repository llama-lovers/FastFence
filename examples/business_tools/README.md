# Simulated business-tools integration

This example intentionally simulates knowledge search, tenant memory and payment
preparation. It is not loaded by `fastfence serve` or included in the product wheel.
It illustrates implementing `ToolsPort` and injecting it into `create_app`.

From the repository root:

```sh
uv run python -m examples.business_tools.server
```

The example listens on **http://127.0.0.1:8001** with its own configuration and
credentials under `state/examples/business-tools/`. It never rewrites the main
product policy or credentials. In a second terminal:

```sh
uv run python -m examples.business_tools.verify
```

All business operations are simulated. Auth, policy enforcement, resource limits,
redaction and audit use the real gateway pipeline. Replace `DemoTools` with your
actual API adapter and explicitly allowlist its names/roles in your own policy.
