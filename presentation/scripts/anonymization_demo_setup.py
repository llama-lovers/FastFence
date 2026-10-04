"""Fresh private keys and explicit echo tool for the reversible privacy demo."""

import base64
import hashlib
import json
import os


class EchoTools:
    def __init__(self):
        self.received = []

    def supports(self, tool):
        return tool == "demo.echo"

    def validate(self, tool, arguments, identity):
        if (
            tool != "demo.echo"
            or set(arguments) != {"text"}
            or not isinstance(arguments["text"], str)
        ):
            raise ValueError("Unsupported echo request")
        return arguments

    async def call(self, tool, arguments, identity):
        self.received.append(arguments["text"])
        return {"text": arguments["text"]}


def build(root, tokens, tools):
    from asymmetric_keys import generate_pair

    from fastfence.app.factory import create_app
    from fastfence.shared.settings.app_settings import AppSettings

    public, private = generate_pair(root / "rsa")
    config = root / "config"
    config.mkdir()
    policy = {
        "version": 1,
        "description": "Isolated real asymmetric privacy demonstration",
        "privacy": {"enabled": True, "input": "redact", "output": "redact"},
        "signatures_enabled": True,
        "semantic": {"provider": "disabled"},
        "tools": {
            "demo.echo": {
                "roles": ["demo"],
                "timeout_ms": 30000,
                "cost_microusd": 0,
            }
        },
        "models": {},
        "text_rules": [],
        "budgets": {
            "demo": {
                "calls": 100,
                "tokens": 1000000,
                "compute_ms": 1000000,
                "cost_microusd": 1000000,
                "concurrent": 2,
            }
        },
        "anonymization": {
            "enabled": True,
            "mode": "reversible",
            "rules": [
                {
                    "id": "person",
                    "operator": "literal",
                    "value": "Anna Kowalska",
                    "replacement": "PERSON",
                    "direction": "both",
                    "target": "all",
                    "allow_restore": True,
                }
            ],
        },
    }
    (config / "policy.yaml").write_text(json.dumps(policy))
    (config / "signatures.json").write_text(
        json.dumps({"version": 1, "signatures": []})
    )
    records = [
        {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "identity": {
                "subject": name,
                "tenant": "privacy-demo",
                "roles": ["demo"],
                "admin": name == "admin",
            },
        }
        for name, token in tokens.items()
    ]
    return create_app(
        AppSettings(
            root=root,
            identity_config_json=json.dumps(records),
            anonymization_keys_json=json.dumps(
                {"local-v1": base64.b64encode(os.urandom(32)).decode()}
            ),
            anonymization_public_key_file=public,
            anonymization_private_key_file=private,
        ),
        tools=tools,
    )
