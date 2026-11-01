"""Generate an RSA keypair used to sign JWTs (RS256).

Run once during setup:

    python scripts/generate_keys.py

Outputs:
    keys/private.pem   (PKCS#8, unencrypted)
    keys/public.pem    (SubjectPublicKeyInfo)

Never commit the output. `keys/` is gitignored on purpose.
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KEYS_DIR = PROJECT_ROOT / "keys"
PRIVATE_PATH = KEYS_DIR / "private.pem"
PUBLIC_PATH = KEYS_DIR / "public.pem"


def main() -> None:
    KEYS_DIR.mkdir(exist_ok=True)

    if PRIVATE_PATH.exists() and PUBLIC_PATH.exists():
        print(f"Keys already exist under {KEYS_DIR}; not regenerating.")
        return

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    PRIVATE_PATH.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    PUBLIC_PATH.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    print(f"Wrote {PRIVATE_PATH}")
    print(f"Wrote {PUBLIC_PATH}")


if __name__ == "__main__":
    main()