"""Profile-local Linz World signing key material."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from hermes_constants import get_hermes_home


@dataclass(frozen=True)
class LinzKeyMaterial:
    private_key_path: str
    public_key_path: str
    private_key_pem: str
    public_key_pem: str
    public_key_type: str
    fingerprint: str


def ensure_key_material(
    profile_id: str,
    *,
    private_key_path: str = "",
    public_key_path: str = "",
) -> LinzKeyMaterial:
    profile = _safe_profile_id(profile_id)
    key_dir = get_hermes_home() / "linz_world" / "keys"
    private_path = Path(private_key_path) if private_key_path else key_dir / f"{profile}.private.pem"
    public_path = Path(public_key_path) if public_key_path else key_dir / f"{profile}.public.pem"
    try:
        private_pem = private_path.read_text(encoding="utf-8")
        public_pem = public_path.read_text(encoding="utf-8")
    except OSError:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_bytes(private_bytes)
        public_path.write_bytes(public_bytes)
        private_pem = private_bytes.decode("utf-8")
        public_pem = public_bytes.decode("utf-8")
    return LinzKeyMaterial(
        private_key_path=str(private_path),
        public_key_path=str(public_path),
        private_key_pem=private_pem,
        public_key_pem=public_pem,
        public_key_type="RSA",
        fingerprint=hashlib.sha256(public_pem.encode("utf-8")).hexdigest(),
    )


def sign_with_private_key(private_key_path: str, payload: str) -> str:
    private_key = serialization.load_pem_private_key(
        Path(private_key_path).read_bytes(),
        password=None,
    )
    signature = private_key.sign(
        str(payload).encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("ascii")


def _safe_profile_id(profile_id: str) -> str:
    raw = str(profile_id or "default").strip() or "default"
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw)
