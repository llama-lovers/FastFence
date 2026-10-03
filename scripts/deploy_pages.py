"""Deploy a verified Pages artifact using its actual documentation-history SHA.

Source provenance stays in mike metadata. The Pages build identity is the generated
site commit, because a dev and stable artifact can share the same source commit.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_RESPONSE = 1024 * 1024
API = "https://api.github.com"
PENDING = {
    "deployment_queued",
    "deployment_in_progress",
    "deployment_pending",
    "queued",
    "in_progress",
    "pending",
    "deployment_attempt_error",
    "unknown_status",
    "not_found",
}
FAILED = {
    "deployment_failed",
    "deployment_content_failed",
    "deployment_cancelled",
    "deployment_lost",
}


class DeploymentError(Exception):
    """Static operator-facing error; never includes provider bodies or tokens."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, token, *, data=None, timeout=20):
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "FastFence-Pages-deployment",
    }
    body = None if data is None else json.dumps(data).encode()
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    deadline = time.monotonic() + timeout
    try:
        with opener.open(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise DeploymentError("Pages API rejected the request")
            chunks = []
            size = 0
            while True:
                if time.monotonic() >= deadline:
                    raise DeploymentError("Pages API response timed out")
                chunk = response.read1(min(65536, MAX_RESPONSE + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE:
                    raise DeploymentError(
                        "Pages API response exceeded its size limit"
                    )
                chunks.append(chunk)
            payload = b"".join(chunks)
        value = json.loads(payload) if payload else {}
        if not isinstance(value, dict):
            raise DeploymentError("Pages API returned an invalid response")
        return value
    except (
        OSError,
        urllib.error.HTTPError,
        ValueError,
        RecursionError,
    ):
        raise DeploymentError(
            "Pages API request failed; credentials and response withheld"
        ) from None


def oidc_token(environment, request):
    url = environment.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    token = environment.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".actions.githubusercontent.com")
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.port not in (None, 443)
        or not token
    ):
        raise DeploymentError(
            "A trusted GitHub Actions OIDC endpoint is required"
        )
    value = request(url, token).get("value")
    if not isinstance(value, str) or not value or len(value) > 65536:
        raise DeploymentError(
            "GitHub Actions returned an invalid identity token"
        )
    return value


def validate_inputs(artifact_id, pages_sha, environment, timeout):
    if not re.fullmatch(r"[0-9a-f]{40}", pages_sha):
        raise DeploymentError(
            "An exact documentation-history commit SHA is required"
        )
    if (
        not isinstance(artifact_id, int)
        or isinstance(artifact_id, bool)
        or not 0 < artifact_id < 2**63
    ):
        raise DeploymentError("A valid uploaded artifact ID is required")
    if not 0 < timeout <= 600:
        raise DeploymentError("Deployment timeout must be within 600 seconds")
    repository = environment.get("GITHUB_REPOSITORY", "")
    token = environment.get("GITHUB_TOKEN", "")
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not token
    ):
        raise DeploymentError(
            "GitHub repository and deployment credentials are required"
        )
    return repository, token


def deploy(
    artifact_id,
    pages_sha,
    environment,
    *,
    request=request_json,
    clock=time.monotonic,
    sleep=time.sleep,
    timeout=600,
):
    repository, token = validate_inputs(
        artifact_id, pages_sha, environment, timeout
    )
    deadline = clock() + timeout
    endpoint = f"{API}/repos/{repository}/pages/deployments"
    identity = oidc_token(environment, request)
    created = request(
        endpoint,
        token,
        data={
            "artifact_id": artifact_id,
            "pages_build_version": pages_sha,
            "oidc_token": identity,
        },
    )
    deployment_id = created.get("id", pages_sha)
    if (
        not isinstance(deployment_id, str | int)
        or isinstance(deployment_id, bool)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(deployment_id))
    ):
        raise DeploymentError(
            "Pages API returned an invalid deployment identifier"
        )
    status_endpoint = endpoint + "/" + str(deployment_id)
    try:
        while clock() < deadline:
            status = request(
                status_endpoint,
                token,
                timeout=min(20, max(0.1, deadline - clock())),
            ).get("status")
            if not isinstance(status, str):
                raise DeploymentError(
                    "Pages API returned an invalid deployment state"
                )
            if status == "succeed":
                return "https://fastfence.dev/"
            if status in FAILED:
                raise DeploymentError(
                    "GitHub Pages reported a failed deployment"
                )
            if status not in PENDING:
                raise DeploymentError(
                    "GitHub Pages returned an unknown deployment state"
                )
            sleep(min(5, max(0, deadline - clock())))
        raise DeploymentError("GitHub Pages deployment timed out")
    except (DeploymentError, KeyboardInterrupt):
        try:
            request(status_endpoint + "/cancel", token, data={}, timeout=10)
        except DeploymentError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--pages-sha", required=True)
    args = parser.parse_args()
    try:
        page_url = deploy(args.artifact_id, args.pages_sha, os.environ)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with Path(output).open("a") as stream:
                stream.write(f"page_url={page_url}\n")
        print(
            "GitHub Pages accepted the documentation snapshot; verify its public content next."
        )
    except (DeploymentError, OSError, ValueError):
        print(
            "Pages deployment failed. Check workflow prerequisites and GitHub status; sensitive details withheld.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print(
            "Pages deployment interrupted; cancellation requested.",
            file=sys.stderr,
        )
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
