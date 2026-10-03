# Public/private-key anonymization

This example adds **RSA public-key encryption and private-key recovery** to stateless reversible anonymization. It uses RSA-3072 OAEP-SHA256 to wrap a fresh AES-256-GCM key for each token. A separate issuer authentication key, derived from the existing local keyring, authenticates the complete envelope before RSA decryption. The implementation uses the [cryptography RSA](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/) and [AEAD](https://cryptography.io/en/latest/hazmat/primitives/aead/) primitives.

No conversation database or plaintext mapping is created. Token verification remains bound to the trusted tenant, subject, active rule fingerprint and expiry. Stable scoped identifiers distinguish equal original values; encrypted tokens remain randomized.

## 1. Generate keys once

After [installing FastFence](../getting-started.md) and extracting the [examples archive](../downloads/fastfence-examples.zip) into `examples/`, run from your installation directory:

```sh
fastfence init --anonymization
python examples/asymmetric_keys.py
```

The first command provisions the existing private issuer keyring if absent. The second creates `state/private/anonymization-rsa/public.pem` and `private.pem` with mode `0600`. It refuses to overwrite either file. Re-running it is not a key rotation command.

The complete executable key generator is embedded from its source:

<!-- source: examples/docs/asymmetric_keys.py -->

## 2. Configure the gateway

Set both paths in the shell that starts FastFence, or add these two settings to your own `.env`:

```sh
export FASTFENCE_ANONYMIZATION_PUBLIC_KEY_FILE=state/private/anonymization-rsa/public.pem
export FASTFENCE_ANONYMIZATION_PRIVATE_KEY_FILE=state/private/anonymization-rsa/private.pem
fastfence doctor
fastfence serve
```

Relative RSA paths resolve against `FASTFENCE_ROOT` (the working directory by default). Both PEM files must describe the same RSA-3072 key pair with public exponent 65537. The existing `state/anonymization-keys.json` issuer keyring remains required: public-key encryption alone does not authenticate who issued a token or produce the stable keyed aliases.

Keys are loaded once at startup. Restart the gateway after changing key settings. The full gateway requires the private key even when response restoration is off, because it decrypts received tokens internally to apply current security checks. A public-only forwarding gateway or client-held-only recovery mode is not implemented.

Keep `private.pem` and the issuer keyring private and out of Git. The public PEM can be distributed as a public encryption key; possession of it alone does not let a caller forge an accepted FastFence token.

## 3. Enable a reversible rule

In **Policies → Add anonymization rule**, use a literal match such as `Anna Kowalska`, replacement label `PERSON`, and the intended input/output and model/tool scope. Permit explicit restoration if you want that option. Review the candidate configuration and set recovery mode to **Reversible** in the settings form before activation.

The relevant policy section is shown below. Merge it into a complete policy rather than replacing the entire file:

```yaml
anonymization:
  enabled: true
  mode: reversible
  rules:
    - id: person
      operator: literal
      value: Anna Kowalska
      replacement: PERSON
      direction: both
      target: all
      allow_restore: true
```

With the RSA pair configured, newly issued reversible tokens start with `[FFR2.`. Existing symmetric `[FFR1.` tokens remain verifiable while their issuer key and matching rule remain available and they have not expired. Irreversible `[FFI1.` behavior is unchanged.

## 4. Verify input and output behavior

Use the [protected request example](protected-request.md) or **Test requests** to send text covered by the rule. With restoration off, the model receives a token and the response retains protected values. With the request's `restore_originals: true` and the rule's `allow_restore: true`, the gateway can recover complete valid tokens in the delivered response.

Model responses can omit or change tokens. FastFence does not reconstruct incomplete ciphertext or guess a missing original. Output privacy and block controls still apply after restoration; a restoration permission does not override them.

## Key lifetime and performance

This implementation loads **one RSA recipient pair**. Replacing it makes earlier FFR2 tokens unreadable, even if the issuer keyring retains old issuer keys. Keep the original pair for the required recovery period or wait for issued tokens to expire before switching; automatic multi-recipient rotation is not implemented. Removing an issuer key also revokes the tokens it authenticates.

RSA envelopes add bytes and asymmetric operations relative to symmetric tokens. Configuration is read only at startup, but this mode is not claimed to have the same latency as local literal matching. Existing token length, value length, request size and replacement-count limits still apply; oversized values fail closed.
