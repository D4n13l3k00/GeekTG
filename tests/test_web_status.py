"""HTTP-level tests for the dashboard status / backup / restore / logout flows."""

import io
import os
import time
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from friendly_telegram.web import core, status


@pytest.fixture
async def web_client(tmp_data_dir):
    w = core.Web(api_token=None, data_root=str(tmp_data_dir),
                 connection=None, hosting=False, default_app=False, proxy=None)
    # Plant something to back up
    (tmp_data_dir / "config.json").write_text('{"hello": "world"}')
    fake = MagicMock()
    sent = MagicMock(); sent.id = 17
    fake.send_message = AsyncMock(return_value=sent)
    fake.delete_messages = AsyncMock()
    fake.log_out = AsyncMock(return_value=True)
    # MagicMock auto-creates `.inline` on access; restrict it so _bot_info
    # gets a real None and the /status JSON serialiser doesn't see a Mock.
    loader_stub = MagicMock(spec=[])
    w.client_data[1] = (loader_stub, fake, MagicMock())
    async with TestClient(TestServer(w.app)) as cli:
        yield cli, w, fake


# ---------- /status ----------

class TestStatusEndpoint:
    async def test_returns_json(self, web_client):
        cli, w, _ = web_client
        r = await cli.get("/status")
        assert r.status == 200
        body = await r.json()
        assert body["version"]
        assert "uptime_seconds" in body
        assert "platform" in body
        assert "data_dir" in body
        assert body["authorized"] is True

    async def test_bot_section_for_no_inline(self, web_client):
        cli, *_ = web_client
        body = await (await cli.get("/status")).json()
        # No inline manager attached → configured=False
        assert body["bot"] == {
            "configured": False, "ready": False, "username": None,
        }

    async def test_resources_disk_present(self, web_client):
        cli, *_ = web_client
        body = await (await cli.get("/status")).json()
        # disk is always reported regardless of psutil availability
        assert "disk" in body["resources"]
        d = body["resources"]["disk"]
        assert d["total_bytes"] > 0
        assert d["free_bytes"] >= 0


# ---------- /ping (alias /is_restart_complete) ----------

class TestPing:
    @pytest.mark.parametrize("path", ["/ping", "/is_restart_complete"])
    async def test_returns_200(self, web_client, path):
        cli, *_ = web_client
        r = await cli.get(path)
        assert r.status == 200


# ---------- /backup TG-code 2FA flow ----------

class TestBackupGate:
    async def test_unauthenticated_get_rejected(self, web_client):
        cli, *_ = web_client
        r = await cli.get("/backup")
        assert r.status == 403

    async def test_full_flow(self, web_client):
        cli, w, _ = web_client
        # Step 1: request → DB stores a code, message goes to Saved Messages
        r = await cli.post("/backup/request")
        assert r.status == 200
        code = w.ctx.backup_gate._pending["code"]
        assert len(code) == 6 and code.isdigit()

        # Step 2: confirm with the code → token returned
        r = await cli.post("/backup/confirm", data=code)
        assert r.status == 200
        body = await r.json()
        token = body["token"]
        assert len(token) >= 16  # opaque random token

        # Step 3: download with the token → 200 zip
        r = await cli.get(f"/backup?token={token}")
        assert r.status == 200
        zb = await r.read()
        assert zipfile.is_zipfile(io.BytesIO(zb))

        # Token is valid for the whole window (not one-shot)
        r2 = await cli.get(f"/backup?token={token}")
        assert r2.status == 200

    async def test_wrong_code_rejected(self, web_client):
        cli, *_ = web_client
        await cli.post("/backup/request")
        r = await cli.post("/backup/confirm", data="999999")
        assert r.status == 403
        assert (await r.json())["error"] == "wrong"

    async def test_expired_token_rejected(self, web_client):
        cli, w, _ = web_client
        await cli.post("/backup/request")
        code = w.ctx.backup_gate._pending["code"]
        token = (await (await cli.post("/backup/confirm", data=code)).json())["token"]
        # Hop over the TTL
        w.ctx.backup_gate._token["expires"] = time.monotonic() - 1
        r = await cli.get(f"/backup?token={token}")
        assert r.status == 403


# ---------- /restore: zip integrity + path traversal ----------

class TestRestoreSafety:
    async def _confirm(self, cli, w):
        await cli.post("/restore/request")
        code = w.ctx.restore_gate._pending["code"]
        return (await (await cli.post("/restore/confirm", data=code)).json())["token"]

    async def test_zip_round_trip(self, web_client):
        cli, w, _ = web_client
        # Backup → mutate → restore
        token_b = (await self._setup_backup(cli, w))
        zb = await (await cli.get(f"/backup?token={token_b}")).read()
        os.remove(os.path.join(w.ctx.effective_data_dir(), "config.json"))

        token_r = await self._confirm(cli, w)
        from aiohttp import FormData
        fd = FormData()
        fd.add_field("backup", zb, filename="b.zip", content_type="application/zip")
        r = await cli.post(f"/restore?token={token_r}", data=fd)
        assert r.status == 200, await r.text()
        assert os.path.exists(os.path.join(w.ctx.effective_data_dir(), "config.json"))

    async def test_path_traversal_rejected(self, web_client):
        cli, w, _ = web_client
        token = await self._confirm(cli, w)
        evil = io.BytesIO()
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("../etc/evil", "pwn")
        from aiohttp import FormData
        fd = FormData()
        fd.add_field("backup", evil.getvalue(), filename="b.zip",
                     content_type="application/zip")
        r = await cli.post(f"/restore?token={token}", data=fd)
        assert r.status == 400
        assert "unsafe path" in (await r.text())

    async def _setup_backup(self, cli, w):
        await cli.post("/backup/request")
        code = w.ctx.backup_gate._pending["code"]
        return (await (await cli.post("/backup/confirm", data=code)).json())["token"]


# ---------- /logout: confirms its destructive plan ----------

class TestLogout:
    async def test_unauthenticated_rejected(self, web_client):
        cli, *_ = web_client
        r = await cli.post("/logout")
        assert r.status == 403

    async def test_full_flow_calls_log_out_and_signals(self, web_client):
        cli, w, fake = web_client
        await cli.post("/logout/request")
        code = w.ctx.logout_gate._pending["code"]
        token = (await (await cli.post("/logout/confirm", data=code)).json())["token"]

        with patch("os.kill") as kill, patch("atexit.register") as atexit_reg:
            r = await cli.post(f"/logout?token={token}")
            assert r.status == 200
            # Background task does the work — give it a tick
            import asyncio
            await asyncio.sleep(0.5)

        fake.send_message.assert_awaited()        # goodbye message
        fake.log_out.assert_awaited()             # session revoked
        atexit_reg.assert_called()                # re-exec scheduled
        kill.assert_called_once()                 # SIGTERM sent
