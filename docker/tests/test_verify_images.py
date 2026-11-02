"""The audit must catch keys even in deleted files from an earlier layer."""

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "verify_images", Path(__file__).parents[1] / "verify_images.py"
)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def layer(name: str, content: bytes) -> io.BytesIO:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        entry = tarfile.TarInfo(name)
        entry.size = len(content)
        archive.addfile(entry, io.BytesIO(content))
    data.seek(0)
    return data


def test_clean_layer() -> None:
    assert audit.scan_layer(layer("app/main.py", b"print('hello')"), [b"secret-key"]) == 1


def test_key_in_earlier_layer_is_refused_without_echoing_it() -> None:
    with pytest.raises(ValueError, match="credential") as error:
        audit.scan_layer(layer("app/old.txt", b"prefix secret-key suffix"), [b"secret-key"])
    assert "secret-key" not in str(error.value)


def test_dotenv_in_image_is_refused() -> None:
    with pytest.raises(ValueError, match="Environment file"):
        audit.scan_layer(layer("app/.env", b"PROVIDER=fake"), [])


def test_key_across_read_boundary_is_refused() -> None:
    content = b"x" * (1024 * 1024 - 3) + b"secret-key"
    with pytest.raises(ValueError, match="credential"):
        audit.scan_layer(layer("app/large.bin", content), [b"secret-key"])
