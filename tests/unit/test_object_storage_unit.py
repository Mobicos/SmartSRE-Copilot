"""Unit tests for app.infrastructure.object_storage — local and minio adapters."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.object_storage import (
    DeletedObject,
    LocalObjectStorageAdapter,
    MinioObjectStorageAdapter,
    StoredObject,
    _content_type_for_key,
    _safe_local_path,
)

# ---------------------------------------------------------------------------
# _safe_local_path
# ---------------------------------------------------------------------------


class TestSafeLocalPath:
    def test_simple_key(self, tmp_path: Path):
        result = _safe_local_path(tmp_path, "docs/file.md")
        assert result == (tmp_path / "docs/file.md").resolve()

    def test_leading_slash_stripped(self, tmp_path: Path):
        result = _safe_local_path(tmp_path, "/docs/file.md")
        assert result == (tmp_path / "docs/file.md").resolve()

    def test_backslash_normalized(self, tmp_path: Path):
        result = _safe_local_path(tmp_path, "docs\\file.md")
        assert result == (tmp_path / "docs/file.md").resolve()

    def test_path_traversal_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="invalid_object_key"):
            _safe_local_path(tmp_path, "../escape.txt")


# ---------------------------------------------------------------------------
# _content_type_for_key
# ---------------------------------------------------------------------------


class TestContentTypeForKey:
    def test_markdown(self):
        assert _content_type_for_key("readme.md") == "text/markdown; charset=utf-8"

    def test_text(self):
        assert _content_type_for_key("notes.txt") == "text/plain; charset=utf-8"

    def test_unknown(self):
        assert _content_type_for_key("data.bin") == "application/octet-stream"

    def test_uppercase(self):
        assert _content_type_for_key("README.MD") == "text/markdown; charset=utf-8"


# ---------------------------------------------------------------------------
# StoredObject / DeletedObject
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_stored_object(self):
        obj = StoredObject(key="k", uri="u", local_path=Path("/tmp"), size=10, backend="local")
        assert obj.key == "k"
        assert obj.size == 10

    def test_deleted_object(self):
        obj = DeletedObject(
            key="k",
            uri="u",
            local_path=Path("/tmp"),
            deleted_local=True,
            deleted_remote=False,
            backend="local",
        )
        assert obj.deleted_local is True
        assert obj.deleted_remote is False


# ---------------------------------------------------------------------------
# LocalObjectStorageAdapter
# ---------------------------------------------------------------------------


class TestLocalObjectStorageAdapter:
    def test_backend(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        assert adapter.backend == "local"

    def test_put_bytes(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        result = adapter.put_bytes("docs/test.txt", b"hello world")
        assert result.key == "docs/test.txt"
        assert result.size == 11
        assert result.backend == "local"
        assert result.local_path.exists()
        assert result.local_path.read_bytes() == b"hello world"

    def test_put_bytes_creates_dirs(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        adapter.put_bytes("a/b/c/file.md", b"content")
        assert (tmp_path / "a/b/c/file.md").exists()

    def test_get_bytes(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        adapter.put_bytes("data.bin", b"\x00\x01")
        assert adapter.get_bytes("data.bin") == b"\x00\x01"

    def test_get_bytes_not_found(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        with pytest.raises(FileNotFoundError, match="object_not_found"):
            adapter.get_bytes("nonexistent")

    def test_delete_existing(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        adapter.put_bytes("to_delete.txt", b"data")
        result = adapter.delete("to_delete.txt")
        assert result.deleted_local is True
        assert result.deleted_remote is False
        assert result.backend == "local"
        assert not result.local_path.exists()

    def test_delete_nonexistent(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        result = adapter.delete("no_such_file.txt")
        assert result.deleted_local is False

    def test_delete_not_a_file(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        # Create a directory with the key name
        dir_path = adapter.local_path_for("a_dir")
        dir_path.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="object_path_is_not_a_file"):
            adapter.delete("a_dir")

    def test_local_path_for(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        path = adapter.local_path_for("some/key.txt")
        assert path == (tmp_path / "some/key.txt").resolve()

    def test_cleanup_local_cache(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        adapter.put_bytes("cache.txt", b"data")
        assert adapter.local_path_for("cache.txt").exists()
        adapter.cleanup_local_cache("cache.txt")
        assert not adapter.local_path_for("cache.txt").exists()

    def test_cleanup_local_cache_nonexistent(self, tmp_path: Path):
        adapter = LocalObjectStorageAdapter(root=tmp_path)
        # Should not raise
        adapter.cleanup_local_cache("no_such_file.txt")


# ---------------------------------------------------------------------------
# MinioObjectStorageAdapter
# ---------------------------------------------------------------------------


class TestMinioObjectStorageAdapter:
    def _make_adapter(self, tmp_path: Path):
        return MinioObjectStorageAdapter(
            endpoint="localhost:9000",
            access_key="key",
            secret_key="secret",
            bucket="test-bucket",
            secure=False,
            local_cache_root=tmp_path,
        )

    def test_backend(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        assert adapter.backend == "minio"

    def test_put_bytes(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = False
        adapter._client = mock_client

        result = adapter.put_bytes("docs/test.md", b"content")
        assert result.key == "docs/test.md"
        assert result.size == 7
        assert result.uri == "minio://test-bucket/docs/test.md"
        assert result.backend == "minio"
        mock_client.make_bucket.assert_called_once_with("test-bucket")
        mock_client.put_object.assert_called_once()

    def test_put_bytes_existing_bucket(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        adapter._client = mock_client

        adapter.put_bytes("file.txt", b"data")
        mock_client.make_bucket.assert_not_called()
        mock_client.put_object.assert_called_once()

    def test_delete_local_and_remote(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        mock_client = MagicMock()
        adapter._client = mock_client

        # Create a local file first
        adapter.put_bytes("del.txt", b"data")
        result = adapter.delete("del.txt")
        assert result.deleted_local is True
        assert result.deleted_remote is True
        mock_client.remove_object.assert_called_once_with("test-bucket", "del.txt")

    def test_delete_remote_nosuchkey(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        mock_client = MagicMock()
        mock_client.remove_object.side_effect = Exception("NoSuchKey not found")
        adapter._client = mock_client

        result = adapter.delete("missing.txt")
        assert result.deleted_remote is False

    def test_delete_remote_other_error(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        mock_client = MagicMock()
        mock_client.remove_object.side_effect = RuntimeError("connection refused")
        adapter._client = mock_client

        with pytest.raises(RuntimeError, match="connection refused"):
            adapter.delete("file.txt")

    def test_delete_not_a_file(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        mock_client = MagicMock()
        adapter._client = mock_client

        dir_path = adapter.local_path_for("a_dir")
        dir_path.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="object_path_is_not_a_file"):
            adapter.delete("a_dir")

    def test_get_bytes(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"content"
        mock_client.get_object.return_value = mock_response
        adapter._client = mock_client

        data = adapter.get_bytes("file.txt")
        assert data == b"content"
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()

    def test_cleanup_local_cache(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        mock_client = MagicMock()
        adapter._client = mock_client

        # Create a local cache file
        adapter.put_bytes("cached.bin", b"data")
        assert adapter.local_path_for("cached.bin").exists()
        adapter.cleanup_local_cache("cached.bin")
        assert not adapter.local_path_for("cached.bin").exists()

    def test_get_client_caches(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        assert adapter._client is None
        mock_client = MagicMock()
        adapter._client = mock_client
        assert adapter._get_client() is mock_client

    def test_get_client_import_error(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        adapter._client = None
        with patch.dict("sys.modules", {"minio": None}):
            with pytest.raises(RuntimeError, match="minio"):
                adapter._get_client()

    def test_get_client_initializes_minio(self, tmp_path: Path):
        adapter = self._make_adapter(tmp_path)
        adapter._client = None
        mock_minio_cls = MagicMock()
        mock_minio_instance = MagicMock()
        mock_minio_cls.return_value = mock_minio_instance
        mock_minio_module = MagicMock()
        mock_minio_module.Minio = mock_minio_cls
        with patch.dict("sys.modules", {"minio": mock_minio_module}):
            result = adapter._get_client()
            assert result is mock_minio_instance
            mock_minio_cls.assert_called_once_with(
                "localhost:9000",
                access_key="key",
                secret_key="secret",
                secure=False,
            )
