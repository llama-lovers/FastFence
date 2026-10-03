# Package installation and PyPI releases

FastFence builds a Python 3.12 wheel and source distribution. The wheel contains
the console assets, default policy/signatures, and reviewed Laya worker/authoring
helpers. It excludes private state, credentials, model weights and downloaded
upstream source. Models and the pinned Laya environment are installed explicitly
after package installation.

This page describes the prepared release process. Verify the package's public
PyPI page before announcing a successful publication or directing users to an
index installation. A built artifact or completed local check alone is not a
published release.

## Verify a local distribution

From a clean source checkout:

```sh
uv build
uvx --from twine==7.0.0 twine check dist/*
uv run python scripts/smoke_wheel.py dist/fastfence-1.0.1-py3-none-any.whl
```

The smoke script creates a fresh Python 3.12 environment and installs the wheel
outside the checkout. It initializes a new workspace, checks the installed CLI,
stages packaged Laya helpers, serves the actual console assets, and confirms that
missing model dependencies fail closed. It performs no model download or live
inference and removes its temporary workspace afterward.

For release acceptance with Ollama and both default Qwen models already running,
also execute the full installed-package path:

```sh
uv run python scripts/smoke_wheel.py dist/fastfence-1.0.1-py3-none-any.whl --full
```

This additionally runs the installed `setup-laya` command, downloads and installs
the pinned upstream in the temporary workspace, and checks an actual benign
completion plus a semantic attack block before business execution. This is a
separate local acceptance run; hosted CI does not claim GPU/model inference.

To try that wheel manually, use a fresh working directory and a Python 3.12
environment:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install /absolute/path/to/fastfence-1.0.1-py3-none-any.whl
fastfence init --anonymization
python -m pip install uv
fastfence setup-laya
```

`setup-laya` requires Git and a POSIX shell. It stages the helper files beneath
`integrations/laya` in the configured root, downloads Laya at commit
`b3b998c03dc44076675305581eb4640b9bf6ff8f`, and installs the upstream dependency
lock with required hashes into `state/laya/venv`. Existing customized helper files
are preserved and cause setup to stop; choose a new `FASTFENCE_AUTHORING_ROOT`
when installing a different helper revision alongside an existing installation.

Install Ollama separately, start `ollama serve` in another terminal, then run:

```sh
ollama pull qwen3:4b
ollama pull qwen3:0.6b
fastfence doctor
fastfence serve
```

Open `http://127.0.0.1:8000`. Initialization prints the private credential-file
location. Connect its management and agent identities in the console and send
your own sample. Laya handles semantic assessment; the business model remains
separately configurable. See [upstream configuration](../docs/examples/openai-upstream.md).
Install OCR separately from the same package environment when needed:

```sh
fastfence setup-ocr
fastfence serve
```

This creates `state/private/ocr-env` using the packaged hash-locked dependency
list, downloads the reviewed mobile OCR model names into
`state/private/ocr-models`, and leaves the gateway environment unchanged. Restart
the gateway to detect these paths. Use the same `--state` option or
`FASTFENCE_STATE` value for setup and serving if you keep state elsewhere. The
large optional OCR downloads are not performed by the default wheel smoke test.
Verify the installed OCR setup and actual synthetic image recognition separately:

```sh
uv run python scripts/smoke_wheel.py dist/fastfence-1.0.1-py3-none-any.whl --ocr
```

## Configure the trusted publisher

For the existing `fastfence` PyPI project, configure its Trusted Publisher in
the project publishing settings using these exact values:

| Field | Value |
| --- | --- |
| PyPI project | `fastfence` |
| GitHub owner | `llama-lovers` |
| Repository | `FastFence` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

The GitHub repository is now `llama-lovers/FastFence`. After a repository rename,
update the repository name in the existing PyPI Trusted Publisher before
publishing; GitHub redirects do not update the OIDC identity expected by PyPI.
See PyPI's [repository rename troubleshooting](https://docs.pypi.org/trusted-publishers/troubleshooting/#token-minting).

Create the matching GitHub environment `pypi`. If the PyPI name is already owned,
its owner must configure this publisher on the existing project. An absent JSON
API response is an availability signal, not proof that the name is claimable.
PyPI documents [pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [publishing with GitHub OIDC](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

The workflow uses an exact commit of the official PyPA publishing action. Only
the publish job receives `id-token: write`; build and test jobs cannot mint a
PyPI upload token. No long-lived PyPI credential is stored in the repository or
required by the workflow. The action creates publication attestations using the
trusted identity.

## Publish the reviewed version

Set the version in `_version.py`, merge the reviewed changes to `main`, and ensure
the verification workflow passes. For version `1.0.1`:

```sh
git tag v1.0.1
git push origin v1.0.1
```

Pushing the tag automatically starts `.github/workflows/publish.yml`. The workflow
checks that the tag is an actual Git tag, matches the package version, and belongs
to `main`; runs tests; builds the sdist and wheel; validates metadata; installs and
tests the wheel in a fresh environment; and passes those exact artifacts to the
separate publication job.

For an existing reviewed tag, the same workflow can be launched explicitly:

```sh
gh workflow run publish.yml --ref main -f tag=v1.0.1
gh run list --workflow publish.yml
```

After publication, the `verify-pypi` job checks out the same release tag with read-only repository permission. It reads [exact-version public PyPI metadata](https://docs.pypi.org/api/json/#get-a-release), downloads the wheel from `files.pythonhosted.org`, and verifies its length and SHA256 against both that metadata and the pre-publication build artifact. Missing public metadata/files are retried up to twelve times with ten-second delays; each network operation has a fifteen-second timeout.

It then installs **`fastfence==VERSION` from `https://pypi.org/simple`** in a new Python 3.12 environment outside the checkout. User index configuration, inherited FastFence settings and `PYTHONPATH` are excluded; install caching is disabled. Installation gets at most three attempts for index propagation. The script checks the installed version, import location and every packaged `fastfence/` file against the verified public wheel before running the same CLI, initialization, helpers, HTTP assets and fail-closed invocation checks as the pre-publication smoke. It does not claim live model or OCR inference.

Successful evidence is retained as the `pypi-verification` Actions artifact. Reproduce the public-package check for a released version without building or installing source:

```sh
python3.12 scripts/smoke_pypi.py 1.0.1 --output pypi-verification.json
```

The script requires `uv` on `PATH`; it uses only the Python standard library before creating the isolated environment. Add `--expected-wheel /path/to/verified.whl` and `--expected-sdist /path/to/verified.tar.gz` to compare both artifacts against your reviewed build as the workflow does. A failed post-publication check fails the workflow; it cannot remove an already published release. Investigate and release a corrected version before announcing success. PyPI release
files cannot be replaced in place; use a new version for corrected artifacts.
Retries skip files already present on PyPI, then verify both wheel and source distribution against the retained build before proceeding. A different existing artifact fails integrity verification. A corrected artifact requires a new version; existing release files are never replaced.

## Verify Agent Communication Protocol from the package

The release workflow also runs actual official ACP SDK peers against the installed gateway, both before publication and after the public-index installation:

```sh
python3.12 scripts/smoke_acp_package.py --wheel dist/fastfence-1.0.1-py3-none-any.whl --output acp-wheel-verification.json
python3.12 scripts/smoke_acp_package.py --pypi-version 1.0.1 --output acp-pypi-verification.json
```

The script creates two fresh environments outside the checkout. The gateway installs the FastFence distribution with its normal dependencies. A separate peer/client environment installs `acp-sdk==1.0.3`, its compatible `uvicorn==0.35.0`, and `requests==2.34.2` (imported by the SDK server but missing from its declared dependencies); that SDK constraint does not downgrade the gateway. Only explicit public example files and synthetic test inputs are staged into the temporary working directory.

The actual loopback HTTP path checks authenticated discovery, a real uppercase operation, input and output denials, output redaction, reversible output with explicit restoration, and sanitized audit. Direct access to the peer requires a separate private token. These checks need neither Ollama nor a model; they test ACP protocol and policy enforcement, not inference quality. Reports are retained as Actions artifacts alongside the public-package verification result.

## Documentation follows the published package

Ordinary CI builds the documentation with strict validation. Stable public Pages deploys
only after the release workflow verifies the exact package from PyPI, including
its ACP integration. The documentation job checks out that same release tag, so
new examples are published together with the package that supports them.

## Versioned documentation and automatic changelog

The tag pipeline runs the public-package, ACP and `uv tool run` checks before
publishing documentation. Mike preserves release directories and metadata on
`gh-pages`; `latest` points to the greatest stable version and replaying an older
release cannot move it backwards. The first major release is archived from its
original tag. Current documentation includes English and Polish, version-specific
source links and LLM corpora. Root downloads and old page entry URLs remain usable.

After Pages succeeds, the workflow generates a changelog from the previous stable
ancestor tag to the released tag, creates the GitHub release and attaches the
verified wheel and source distribution. Repeated runs preserve existing notes;
interrupted drafts resume asset upload and publication. Do not create the release
manually before the verification pipeline completes.


## Development documentation

`/dev/` contains unreleased documentation from the exact commit of a successful
`Verify FastFence` push run on this repository's `main`. Pull-request, failed and
cancelled runs cannot publish it. Pages uses the same `documentation-history`
concurrency group for development and releases, including both the history push
and deployment, so their preserved `gh-pages` history cannot race. Queuing is
set to `max` so a new development run does not evict a pending release deployment.

The development version is labelled unreleased and links examples to its exact
source SHA. It does not change `latest`, stable version history, the root default,
or stable root downloads and LLM documents. An older or divergent development
commit cannot overwrite the last published development version. Development
features may require that source revision; the stable PyPI package is not claimed
to contain them. When no documentation history exists, the first development build archives only
the already published and independently verified `v1.0.0` release as `latest`.
It never promotes the unreleased working package version to stable.
