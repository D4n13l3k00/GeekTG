"""Local-only DB backend round-trips and edge cases."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from friendly_telegram.database.backend import CloudBackend


@pytest.fixture
async def backend(tmp_data_dir):
    client = MagicMock()
    me = MagicMock()
    me.user_id = 1234
    client.get_me = AsyncMock(return_value=me)
    backend = CloudBackend(client)
    await backend.init(trigger_refresh=lambda *a, **kw: None)
    return backend


class TestConfigRoundTrip:
    async def test_missing_file_returns_empty_json(self, backend):
        assert await backend.do_download() == "{}"

    async def test_upload_then_download(self, backend):
        await backend.do_upload('{"foo": 1}')
        assert await backend.do_download() == '{"foo": 1}'

    async def test_upload_atomic_via_temp(self, backend, tmp_path):
        # If do_upload were non-atomic, an exception mid-write would leave a
        # truncated file. Verify .tmp file is cleaned up on success.
        await backend.do_upload('{"a": 1}')
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == []

    async def test_empty_string_normalises_to_empty_object(self, backend):
        await backend.do_upload("")
        assert await backend.do_download() == "{}"


class TestAssets:
    async def test_store_and_fetch_bytes(self, backend):
        asset_id = await backend.store_asset(b"binary blob")
        assert isinstance(asset_id, int) and asset_id > 0
        assert await backend.fetch_asset(asset_id) == b"binary blob"

    async def test_store_and_fetch_string(self, backend):
        asset_id = await backend.store_asset("hello")
        assert await backend.fetch_asset(asset_id) == b"hello"

    async def test_string_filepath_is_read(self, backend, tmp_path):
        f = tmp_path / "src.bin"
        f.write_bytes(b"from disk")
        asset_id = await backend.store_asset(str(f))
        assert await backend.fetch_asset(asset_id) == b"from disk"

    async def test_fetch_missing_returns_none(self, backend):
        assert await backend.fetch_asset(999999) is None

    async def test_ids_increment(self, backend):
        a = await backend.store_asset(b"one")
        b = await backend.store_asset(b"two")
        c = await backend.store_asset(b"three")
        assert b == a + 1 and c == b + 1
        # Each blob keeps its own contents — no cross-contamination
        assert await backend.fetch_asset(a) == b"one"
        assert await backend.fetch_asset(b) == b"two"
        assert await backend.fetch_asset(c) == b"three"

    async def test_unsupported_type_raises(self, backend):
        with pytest.raises(TypeError):
            await backend.store_asset(object())
