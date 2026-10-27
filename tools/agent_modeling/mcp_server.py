"""MCP server for the Dust3D agent modeling toolkit.

Each tool runs the existing CLI (python -m dust3d_agent ...) in a subprocess, so the
toolkit's own prints never reach the MCP stdio channel.

  DUST3D_BIN         Dust3D binary used for export (required by build_model)
  DUST3D_MODELS_DIR  where models are written (default ~/dust3d-models)

Register in Claude Code:
  claude mcp add dust3d -e DUST3D_BIN=/path/to/dust3d -- /path/to/python /path/to/mcp_server.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from mcp.server.mcpserver import Image, MCPServer

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.expanduser(os.environ.get("DUST3D_MODELS_DIR", "~/dust3d-models"))

server = MCPServer(
    "dust3d",
    instructions="Builds rigged, animated Dust3D models from a JSON spec, headless. "
    "Call get_guide once before writing your first spec, then build_model, look at the "
    "turnaround image and the report, fix the spec and build again until quality.ok is true.",
)


def _run(*args: str, timeout: int = 600) -> dict:
    env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    proc = subprocess.run([sys.executable, "-m", "dust3d_agent", *args], cwd=HERE, env=env,
                          capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "exit_code": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


def _write_spec(spec: dict) -> str:
    name = str(spec.get("name", ""))
    # the name becomes a directory and file names, so keep it to one safe path component
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("spec.name must be 1-64 letters, digits, '_' or '-'")
    outdir = os.path.join(MODELS_DIR, name)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, name + ".json")
    with open(path, "w") as f:
        json.dump(spec, f, indent=2)
    return path


@server.tool()
def get_guide() -> str:
    """The spec format manual (AGENT_GUIDE.md): parts, nodes, rigs, animations and the quality checklist."""
    with open(os.path.join(HERE, "AGENT_GUIDE.md")) as f:
        return f.read()


@server.tool()
def build_model(spec: dict, gif: bool = False) -> list:
    """Compile a spec to .ds3, export .glb with Dust3D, and render previews.

    Files go to DUST3D_MODELS_DIR/<spec.name>/. Returns the build summary (quality, lint,
    seams, metrics, file paths) and the turnaround image. Open the .ds3 in Dust3D to edit by hand.
    """
    path = _write_spec(spec)
    args = ["build", path, "-o", os.path.dirname(path)] + (["--gif"] if gif else [])
    summary = _run(*args)
    result: list = [json.dumps(summary, indent=1)]
    turnaround = summary.get("images", {}).get("turnaround")
    if turnaround and os.path.exists(turnaround):
        result.append(Image(path=turnaround))
    return result


@server.tool()
def lint_spec(spec: dict) -> dict:
    """Check a spec for problems without building it."""
    return _run("lint", _write_spec(spec))


@server.tool()
def decompile(ds3_path: str) -> dict:
    """Turn an existing .ds3 document into a spec you can edit and pass to build_model."""
    ds3_path = os.path.expanduser(ds3_path)
    stem = os.path.splitext(os.path.basename(ds3_path))[0]
    out = os.path.join(MODELS_DIR, stem, stem + ".json")  # decompile writes image assets beside it
    os.makedirs(os.path.dirname(out), exist_ok=True)
    failure = _run("decompile", ds3_path, "-o", out)  # prints nothing on success
    if not os.path.exists(out):
        return failure
    with open(out) as f:
        return {"ok": True, "spec_path": out, "spec": json.load(f)}


@server.tool()
def list_rigs(rig: str | None = None) -> dict:
    """Rig types with their bones and animation types; pass a rig name for bone positions."""
    return _run("rigs", *([rig] if rig else []))


if __name__ == "__main__":
    server.run()
