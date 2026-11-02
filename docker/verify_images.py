"""Audit Compose images without displaying runtime credentials (stdlib only).

Run from the repository root after ``docker compose up --build -d``.
Every saved layer is inspected, including files removed by later layers.
"""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

KEY_NAMES = {"PARSLEY_LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"}


def docker(*args: str) -> str:
    """Capture output; failures deliberately omit potentially secret output."""
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError("Docker audit command failed; check engine/container availability")
    return result.stdout


def provider_setting(name: str) -> bool:
    return name.startswith("PARSLEY_LLM_") or name in KEY_NAMES


def environment(values: Sequence[str]) -> dict[str, str]:
    return dict(value.split("=", 1) for value in values if "=" in value)


def scan_bytes(stream: BinaryIO, secrets: Sequence[bytes]) -> None:
    overlap = max((len(secret) for secret in secrets), default=1) - 1
    tail = b""
    while chunk := stream.read(1024 * 1024):
        data = tail + chunk
        if any(secret in data for secret in secrets if secret):
            raise ValueError("Runtime credential found in image data (value redacted)")
        tail = data[-overlap:] if overlap else b""


def scan_layer(stream: BinaryIO, secrets: Sequence[bytes]) -> int:
    """Read compressed or uncompressed filesystem tar without extracting files."""
    count = 0
    with tarfile.open(fileobj=stream, mode="r|*") as layer:
        for entry in layer:
            if any(part == ".env" or part.startswith(".env.") for part in Path(entry.name).parts):
                raise ValueError("Environment file found in image layer")
            if entry.isfile():
                source = layer.extractfile(entry)
                if source is not None:
                    with source:
                        scan_bytes(source, secrets)
                    count += 1
    return count


def audit_image(image_id: str, secrets: Sequence[bytes]) -> tuple[int, int]:
    metadata = docker("image", "inspect", image_id)
    history = docker("history", "--no-trunc", "--format", "{{json .}}", image_id)
    scan_bytes(io.BytesIO((metadata + history).encode()), secrets)
    config = json.loads(metadata)[0]["Config"]
    if any(provider_setting(name) for name in environment(config.get("Env") or [])):
        raise ValueError("Provider setting baked into image configuration")
    with tempfile.TemporaryDirectory(prefix="parsley-image-audit-") as directory:
        saved = Path(directory) / "image.tar"
        docker("image", "save", "--output", str(saved), image_id)
        with tarfile.open(saved) as archive:
            manifest_file = archive.extractfile("manifest.json")
            if manifest_file is None:
                raise ValueError("Saved image has no Docker manifest")
            with manifest_file:
                manifests = json.load(manifest_file)
            layers = {name for manifest in manifests for name in manifest["Layers"]}
            count = 0
            for name in layers:
                source = archive.extractfile(name)
                if source is None:
                    raise ValueError("Saved image is missing a filesystem layer")
                with source:
                    count += scan_layer(source, secrets)
    return len(layers), count


def main() -> None:
    # Resolved Compose config is captured, never printed: it contains .env values.
    compose = json.loads(docker("compose", "config", "--format", "json"))
    expected = compose["services"]["api"].get("environment", {})
    runtime: dict[str, dict[str, str]] = {}
    images: dict[str, str] = {}
    for service in ("api", "web"):
        container_id = docker("compose", "ps", "-q", service).strip()
        if not container_id:
            raise RuntimeError("Both Compose services must be running")
        container = json.loads(docker("inspect", container_id))[0]
        runtime[service] = environment(container["Config"].get("Env") or [])
        images[service] = container["Image"]
    for name, value in expected.items():
        if provider_setting(name) and runtime["api"].get(name) != value:
            raise ValueError("Runtime provider configuration does not match Compose env_file")
    if any(provider_setting(name) for name in runtime["web"]):
        raise ValueError("Provider configuration exposed to web container")
    secrets = list({value.encode() for name, value in runtime["api"].items() if name in KEY_NAMES and value})
    print("PASS: provider settings match API runtime config; none in web runtime")
    print(f"Runtime keys checked: {len(secrets)} (values never printed)")
    for service, image_id in images.items():
        layers, files = audit_image(image_id, secrets)
        print(f"PASS: {service}: image config + docker history + {layers} layers / {files} files; no .env or runtime key")
    if not secrets:
        print("LIMIT: no runtime key configured; key-value scan had no real credential to compare")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError, tarfile.TarError):
        raise SystemExit("FAIL: image audit failed (details redacted to protect credentials)") from None
