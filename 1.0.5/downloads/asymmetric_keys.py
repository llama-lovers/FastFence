"""Generate an RSA-3072 recipient pair without overwriting any existing file."""

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_pair(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    public_path = directory / "public.pem"
    private_path = directory / "private.pem"
    if public_path.exists() or private_path.exists():
        raise FileExistsError("Refusing to overwrite an existing RSA key pair")
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    values = (
        (
            private_path,
            private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        ),
        (
            public_path,
            private.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        ),
    )
    created = []
    try:
        for path, data in values:
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            created.append(path)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return public_path, private_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("state/private/anonymization-rsa"),
    )
    args = parser.parse_args()
    try:
        public, private = generate_pair(args.directory)
    except OSError as error:
        raise SystemExit(f"Key generation failed: {error}") from None
    print(f"Public encryption key: {public}")
    print(f"Private recovery key: {private}")
    print(
        "Keep private.pem and the issuer keyring private; neither belongs in Git."
    )


if __name__ == "__main__":
    main()
