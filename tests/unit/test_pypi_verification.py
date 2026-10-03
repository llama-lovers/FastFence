"""Release integrity checks must fail before invoking an installed artifact."""

import hashlib
import json
import urllib.error

import pytest

from scripts import smoke_pypi

VERSION = "0.1.2"
CONTENT = b"synthetic-wheel-for-integrity-check"


def metadata():
    return {
        "info": {"name": "fastfence", "version": VERSION},
        "urls": [
            {
                "filename": f"fastfence-{VERSION}-py3-none-any.whl",
                "url": f"https://files.pythonhosted.org/packages/fixture/fastfence-{VERSION}-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "yanked": False,
                "digests": {"sha256": hashlib.sha256(CONTENT).hexdigest()},
                "size": len(CONTENT),
            }
        ],
    }


def install_fixture(monkeypatch, value):
    monkeypatch.setattr(
        smoke_pypi,
        "read_public",
        lambda url, maximum: json.dumps(value).encode()
        if url.endswith("/json")
        else CONTENT,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x["info"].update(version="9.9.9"),
        lambda x: x["info"].update(name="another-project"),
        lambda x: x["urls"][0].update(yanked=True),
        lambda x: x["urls"][0].update(url="https://attacker.test/file.whl"),
        lambda x: x["urls"][0].update(
            url=f"http://files.pythonhosted.org/fastfence-{VERSION}-py3-none-any.whl"
        ),
        lambda x: x["urls"][0].update(size=100_000_000),
        lambda x: x["urls"][0]["digests"].update(sha256="not-a-sha256"),
        lambda x: x["urls"].append(dict(x["urls"][0])),
    ],
)
def test_untrusted_or_wrong_metadata_rejected(monkeypatch, mutation):
    value = metadata()
    mutation(value)
    install_fixture(monkeypatch, value)
    with pytest.raises(ValueError):
        smoke_pypi.wheel_metadata(VERSION)


@pytest.mark.parametrize(
    "version", ["latest", "../x", "0.1", "v0.1.2", "0.1.2;echo bad"]
)
def test_exact_version_required(version):
    with pytest.raises(ValueError):
        smoke_pypi.wheel_metadata(version)


def test_missing_release_retried_then_exact_bytes_saved(monkeypatch, tmp_path):
    attempts = []
    waits = []

    def read(url, maximum):
        if url.endswith("/json"):
            attempts.append(url)
            if len(attempts) == 1:
                raise urllib.error.HTTPError(
                    url, 404, "Not yet visible", {}, None
                )
            return json.dumps(metadata()).encode()
        return CONTENT

    monkeypatch.setattr(smoke_pypi, "read_public", read)
    monkeypatch.setattr(smoke_pypi.time, "sleep", waits.append)
    wheel, digest = smoke_pypi.download_release(
        VERSION, tmp_path, attempts=3, delay=1
    )
    assert wheel.read_bytes() == CONTENT
    assert digest == hashlib.sha256(CONTENT).hexdigest()
    assert len(attempts) == 2 and waits == [1]


def test_missing_wheel_eventually_fails(monkeypatch, tmp_path):
    value = metadata()
    value["urls"] = []
    install_fixture(monkeypatch, value)
    waits = []
    monkeypatch.setattr(smoke_pypi.time, "sleep", waits.append)
    with pytest.raises(RuntimeError, match="retry limit"):
        smoke_pypi.download_release(VERSION, tmp_path, attempts=3, delay=1)
    assert waits == [1, 1]


@pytest.mark.parametrize("field", ["size", "sha256"])
def test_corrupt_download_rejected(monkeypatch, tmp_path, field):
    value = metadata()
    if field == "size":
        value["urls"][0]["size"] += 1
    else:
        value["urls"][0]["digests"]["sha256"] = "a" * 64
    install_fixture(monkeypatch, value)
    with pytest.raises(ValueError, match="SHA256"):
        smoke_pypi.download_release(VERSION, tmp_path, attempts=1)
    assert not list(tmp_path.iterdir())


def test_verified_public_release_reuses_smoke_and_reports(
    monkeypatch, tmp_path
):
    install_fixture(monkeypatch, metadata())
    calls = []
    monkeypatch.setattr(
        smoke_pypi,
        "smoke",
        lambda wheel, **kwargs: calls.append((wheel.read_bytes(), kwargs)),
    )
    expected = tmp_path / f"fastfence-{VERSION}-py3-none-any.whl"
    expected.write_bytes(CONTENT)
    report = tmp_path / "report.json"
    smoke_pypi.verify(VERSION, expected_wheel=expected, output=report)
    assert calls == [(CONTENT, {"pypi_version": VERSION})]
    assert json.loads(report.read_text())["matches_verified_build"] is True


def test_public_build_mismatch_never_installs(monkeypatch, tmp_path):
    install_fixture(monkeypatch, metadata())
    expected = tmp_path / f"fastfence-{VERSION}-py3-none-any.whl"
    expected.write_bytes(b"different")
    monkeypatch.setattr(
        smoke_pypi, "smoke", lambda *a, **kw: pytest.fail("must not install")
    )
    with pytest.raises(ValueError, match="differs"):
        smoke_pypi.verify(VERSION, expected_wheel=expected)


def test_index_installation_uses_public_exact_version_and_bounded_retries(
    monkeypatch, tmp_path
):
    import subprocess

    from scripts import smoke_wheel

    calls, waits = [], []

    def run(command, directory, environment):
        calls.append(command)
        if len(calls) < 3:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(smoke_wheel, "run", run)
    monkeypatch.setattr(smoke_wheel.time, "sleep", waits.append)
    smoke_wheel.install_package(
        tmp_path / "python", tmp_path / "local.whl", tmp_path, {}, VERSION
    )
    assert len(calls) == 3 and waits == [10, 10]
    assert all(command[-1] == "fastfence==0.1.2" for command in calls)
    assert "--no-config" in calls[0] and "--no-cache" in calls[0]
    assert (
        calls[0][calls[0].index("--default-index") + 1]
        == "https://pypi.org/simple"
    )
