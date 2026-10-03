"""Trusted, stateless detect-secrets extension; all examples are synthetic."""

import re

from detect_secrets.plugins.base import BasePlugin, RegexBasedDetector


class CompanyCodeDetector(RegexBasedDetector):
    secret_type = "Synthetic company identifier"  # pragma: allowlist secret
    denylist = (
        re.compile(r"\bACME-DEMO-[0-9]{4}\b"),
        re.compile(re.escape("PROJECT ORCHID INTERNAL"), re.IGNORECASE),
    )


class InternalPhraseDetector(BasePlugin):
    secret_type = "Synthetic internal phrase"  # pragma: allowlist secret

    def analyze_string(self, string):
        phrase = "EXAMPLE INTERNAL ONLY"
        if phrase in string:
            yield phrase


if __name__ == "__main__":
    assert list(CompanyCodeDetector().analyze_string("ACME-DEMO-1234"))
    assert list(CompanyCodeDetector().analyze_string("project orchid internal"))
    assert list(
        InternalPhraseDetector().analyze_string("EXAMPLE INTERNAL ONLY")
    )
    assert not list(CompanyCodeDetector().analyze_string("ordinary report"))
    print("Custom detector example checks passed")
