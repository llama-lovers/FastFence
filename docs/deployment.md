# Deployment

The documentation site targets `https://fastfence.dev` on GitHub Pages. DNS ownership, repository Pages settings and a successful deployment must be verified by the operator; adding this documentation does not prove the domain is already configured.

GitHub Pages hosts the static documentation. Run the FastFence API, dashboard and model service on your own application infrastructure.

## Run the gateway

From the repository root, with Python 3.12 and uv installed:

```sh
uv sync --locked
uv run fastfence init
uv run fastfence serve --host 127.0.0.1 --port 8000
```

Initialization creates private local demo credentials. For deployment, provision token hashes and verified claims through `FASTFENCE_IDENTITY_CONFIG_FILE` or `FASTFENCE_IDENTITY_CONFIG_JSON`. The running gateway needs no writable state directory or application database. See [settings](settings.md) for available environment variables.

Keep model servers and upstream credentials behind the gateway. Expose the API through your infrastructure's HTTPS termination and route protected agent traffic through it. The default bind address is loopback. Business handlers are simulated until you replace them with real validated adapters.

Independent instances can run in parallel, each with a trusted `FASTFENCE_INSTANCE_ID` and local budgets/audit. Accounting resets on restart. Several workers or replicas do not share quotas; deployments requiring a global spending cap need external coordination or consistent subject routing.

## Preview and build documentation

Serve the documentation locally:

```sh
uv run --group docs mkdocs serve --dev-addr 127.0.0.1:8001
```

Open `http://127.0.0.1:8001`; the gateway can continue using port 8000.

Build using only the locked documentation dependency group:

```sh
uv sync --locked --only-group docs
uv run --locked --only-group docs mkdocs build --strict
```

The build writes the generated static site to `site/`. Keep generated output out of Git; publish only that build artifact. Runtime state, bearer credentials and local integration environments are not documentation assets.

## GitHub Pages Actions

In the repository's **Settings → Pages**, select **GitHub Actions** as the publishing source. The documentation workflow validates pull requests and builds/publishes `main`; a pull-request build does not deploy the site.

GitHub Pages is available for public repositories on GitHub Free. Private repositories require a supporting paid plan. If the project remains private without that capability, publish the documentation through a separate public repository or enable an eligible plan before deploying. See [GitHub Pages availability](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

The build uploads the generated site as a Pages artifact. The separate deployment job uses the `github-pages` environment, depends on the successful build, and receives `pages: write` and `id-token: write`. The build job does not need deployment permissions. Review the workflow run and its deployed URL after pushing to `main`. These are the requirements for a [custom GitHub Pages workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Configure fastfence.dev

In **Settings → Pages → Custom domain**, save `fastfence.dev`. At the DNS provider, create these apex records:

| Type | Name | Value |
| --- | --- | --- |
| `A` | `@` | `185.199.108.153` |
| `A` | `@` | `185.199.109.153` |
| `A` | `@` | `185.199.110.153` |
| `A` | `@` | `185.199.111.153` |
| `CNAME` (optional) | `www` | `llama-lovers.github.io` |

The `www` target excludes the repository name. GitHub Pages can redirect `www.fastfence.dev` to the configured apex domain. Avoid wildcard records. Follow [GitHub's custom-domain instructions](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site) and [verify domain ownership](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages).

Check propagation:

```sh
dig fastfence.dev +noall +answer -t A
dig www.fastfence.dev +noall +answer -t CNAME
```

After GitHub validates DNS and provisions the certificate, enable **Enforce HTTPS**. Certificate availability can take up to 24 hours. For Actions deployments, repository Pages settings determine the custom domain; a generated `CNAME` file alone does not configure it. See [GitHub's HTTPS guide](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https).

## Verify the result

Confirm the documentation workflow succeeded, open `https://fastfence.dev`, and check navigation, search and the architecture diagram. Confirm HTTPS and any intended `www` redirect. These checks validate the documentation deployment; gateway health and live model/tool checks are separate application checks.
