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
uv run python scripts/smoke_wheel.py dist/fastfence-0.1.0-py3-none-any.whl
```

The smoke script creates a fresh Python 3.12 environment and installs the wheel
outside the checkout. It initializes a new workspace, checks the installed CLI,
stages packaged Laya helpers, serves the actual console assets, and confirms that
missing model dependencies fail closed. It performs no model download or live
inference and removes its temporary workspace afterward.

For release acceptance with Ollama and both default Qwen models already running,
also execute the full installed-package path:

```sh
uv run python scripts/smoke_wheel.py dist/fastfence-0.1.0-py3-none-any.whl --full
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
python -m pip install /absolute/path/to/fastfence-0.1.0-py3-none-any.whl
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
separately configurable. See [upstream configuration](examples/openai-upstream.md).
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
uv run python scripts/smoke_wheel.py dist/fastfence-0.1.0-py3-none-any.whl --ocr
```

## Configure the trusted publisher

For the first release, add a pending publisher in the intended PyPI owner's
account using these exact values:

| Field | Value |
| --- | --- |
| PyPI project | `fastfence` |
| GitHub owner | `llama-lovers` |
| Repository | `HackYeah2026-challenge-second` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

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
the verification workflow passes. For version `0.1.0`:

```sh
git tag v0.1.0
git push origin v0.1.0
gh release create v0.1.0 --title 'FastFence 0.1.0' --generate-notes
```

Publishing the GitHub release starts `.github/workflows/publish.yml`. The workflow
checks that the tag is an actual Git tag, matches the package version, and belongs
to `main`; runs tests; builds the sdist and wheel; validates metadata; installs and
tests the wheel in a fresh environment; and passes those exact artifacts to the
separate publication job.

For an existing reviewed tag, the same workflow can be launched explicitly:

```sh
gh workflow run publish.yml --ref main -f tag=v0.1.0
gh run list --workflow publish.yml
```

After success, verify both files and their hashes at the public PyPI project,
then perform a fresh index installation outside the checkout. Only then update
the main installation instructions to use the published version. PyPI release
files cannot be replaced in place; use a new version for corrected artifacts.
The workflow intentionally does not skip existing artifacts silently.
