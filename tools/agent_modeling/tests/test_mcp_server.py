import asyncio
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def _call(server, tool, args):
    from mcp import Client

    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)
    return asyncio.run(go())


@pytest.fixture
def server(tmp_path, monkeypatch):
    import mcp_server
    monkeypatch.setattr(mcp_server, "MODELS_DIR", str(tmp_path))
    return mcp_server.server


def test_rejects_unsafe_name(server):
    result = _call(server, "lint_spec", {"spec": {"name": "../evil", "parts": []}})
    assert result.is_error


@pytest.mark.skipif(not os.environ.get("DUST3D_BIN"), reason="needs DUST3D_BIN")
def test_build_fox(server, tmp_path):
    with open(os.path.join(HERE, "examples", "fox.json")) as f:
        spec = json.load(f)
    result = _call(server, "build_model", {"spec": spec})
    assert not result.is_error
    summary = json.loads(result.content[0].text)
    assert summary["ok"], summary
    assert result.content[1].type == "image"
    glb = tmp_path / spec["name"] / (spec["name"] + ".glb")
    assert glb.stat().st_size > 0

    back = _call(server, "decompile", {"ds3_path": str(tmp_path / spec["name"] / (spec["name"] + ".ds3"))})
    assert json.loads(back.content[0].text)["ok"]
