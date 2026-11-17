#!/usr/bin/env python3
"""Creates the RSA key pairs used for Snowflake key-pair authentication (no passwords anywhere):

  admin - your Snowflake admin user, used by run_snowflake.py
  fed   - SVC_DATABRICKS_FED, the least-privileged service user behind the Databricks connection (war story B)

Private keys are written to .secrets/ (git-ignored) and copied to Key Vault. Prints the one-time ALTER USER statement
to run in Snowsight for your admin user. Safe to re-run: existing keys are kept.
"""
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import poc_common as pc  # noqa: E402

SECRETS = pc.ROOT / ".secrets"
KEYS = {"admin": "snowflake-admin-private-key", "fed": "snowflake-fed-private-key"}


def ensure_key(name: str) -> tuple[Path, str]:
    priv = SECRETS / f"snowflake_{name}_rsa_key.p8"
    pub = SECRETS / f"snowflake_{name}_rsa_key.pub"
    if not priv.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
        pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                      serialization.PublicFormat.SubjectPublicKeyInfo))
        print(f"created {priv.relative_to(pc.ROOT)}")
    body = "".join(line for line in pub.read_text().splitlines() if "PUBLIC KEY" not in line)
    return priv, body


def to_key_vault(vault_uri: str, secret: str, priv: Path) -> None:
    from azure.identity import AzureCliCredential
    from azure.keyvault.secrets import SecretClient
    pc.assert_personal_tenant()
    SecretClient(vault_url=vault_uri, credential=AzureCliCredential()).set_secret(secret, priv.read_text())
    print(f"stored {secret} in Key Vault")


def main() -> None:
    SECRETS.mkdir(exist_ok=True)
    st = pc.state()
    out = {}
    for name, secret in KEYS.items():
        priv, pub_body = ensure_key(name)
        out[f"snowflake_{name}_public_key"] = pub_body
        if st.get("keyVaultUri"):
            to_key_vault(st["keyVaultUri"], secret, priv)
    pc.update_state(out)
    admin = pc.settings()["snowflake"]["adminUser"] or "<your_admin_user>"
    print("\nRun this ONCE in a Snowsight worksheet (as your admin user), then use run_snowflake.py:\n")
    print(f"ALTER USER {admin} SET RSA_PUBLIC_KEY='{out['snowflake_admin_public_key']}';\n")


if __name__ == "__main__":
    main()
