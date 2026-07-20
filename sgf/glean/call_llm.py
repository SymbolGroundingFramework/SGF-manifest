#!/usr/bin/env python3
"""
call_llm.py — Thin adapter for llm_wrapper.py

Replaces the old call_llm.py with a direct subprocess call to the
self-contained llm_wrapper.py.  No classes, no dataclasses.

The adapter preserves the same interface so no other GLEAN file needs
to change:
    call_llm(prompt_text, llm_cfg, ...) -> str

It writes the prompt to a temp file, calls llm_wrapper.py as a
subprocess, reads the response, and returns it.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default config when sgf.toml is missing the [llm] section
DEFAULT_LLM_CFG = {
    "wrapper_path": "",
    "runner": "python",
    "tier": "worker",
    "temp": "logical",
    "policy": "",
    "scratch_dir": "",
    "timeout_seconds": 300,
    "keep_scratch_files": False,
}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def load_llm_config(sgf_toml_path: Optional[str] = None) -> dict:
    """Return a minimal LLM config dict.

    Ignores the TOML file entirely — just returns defaults that point
    at llm_wrapper.py next to this script.
    """
    cfg = dict(DEFAULT_LLM_CFG)
    # Auto-detect llm_wrapper.py next to this script
    here = Path(__file__).resolve().parent
    wrapper_path = here / "llm_wrapper.py"
    if wrapper_path.exists():
        cfg["wrapper_path"] = str(wrapper_path)
    return cfg


def is_wrapper_configured(llm_cfg: dict) -> bool:
    """Return True iff the wrapper path is set and the file exists."""
    wp = llm_cfg.get("wrapper_path", "")
    if not wp:
        return False
    return Path(wp).expanduser().exists()


def call_llm(
    prompt_text: str,
    llm_cfg: dict,
    system_text: Optional[str] = None,
    tier: Optional[str] = None,
    temp: Optional[str] = None,
    policy: Optional[str] = None,
) -> str:
    """Invoke llm_wrapper.py as a subprocess.

    Writes the prompt to a temp file, calls llm_wrapper.py with
    --in-file and --out-file, reads the response, and returns it.

    The --source flag is set to 'cloud' (OpenRouter) by default.
    Override by setting llm_cfg['source'] to 'local' for Ollama.

    The --model flag is set from llm_cfg.get('model', '').
    The --temp flag is set from the 'temp' parameter or llm_cfg['temp'].
    """
    wrapper_path = llm_cfg.get("wrapper_path", "")
    if not wrapper_path or not Path(wrapper_path).expanduser().exists():
        raise RuntimeError(
            "LLM wrapper not found. Set wrapper_path in llm_cfg or "
            "place llm_wrapper.py next to this script."
        )

    scratch_dir_str = llm_cfg.get("scratch_dir", "")
    scratch_dir = Path(scratch_dir_str).expanduser() if scratch_dir_str \
        else Path(tempfile.gettempdir())
    scratch_dir.mkdir(parents=True, exist_ok=True)

    tag = secrets.token_hex(4)
    in_file = scratch_dir / f"glean_llm_{tag}.in.txt"
    out_file = scratch_dir / f"glean_llm_{tag}.out.txt"

    # Write the prompt file
    in_file.write_text(prompt_text, encoding="utf-8")

    # Build the subprocess command
    source = llm_cfg.get("source", "cloud")
    model = llm_cfg.get("model", "")
    temp_val = temp or llm_cfg.get("temp", "")
    timeout = int(llm_cfg.get("timeout_seconds", 300))
    keep = bool(llm_cfg.get("keep_scratch_files", False))

    cmd = [
        sys.executable,
        str(Path(wrapper_path).expanduser()),
        "--in-file", str(in_file),
        "--out-file", str(out_file),
        "--source", source,
    ]

    if model:
        cmd.extend(["--model", model])
    if temp_val:
        cmd.extend(["--temp", temp_val])

    # Run the subprocess
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            tail_err = (result.stderr or "")[-500:]
            raise RuntimeError(
                f"llm_wrapper.py exited {result.returncode}. "
                f"stderr tail: {tail_err!r}"
            )
        if not out_file.exists():
            raise RuntimeError(
                f"llm_wrapper.py exited 0 but did not write {out_file}"
            )
        response = out_file.read_text(encoding="utf-8")
        return response
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"llm_wrapper.py timed out after {timeout}s"
        )
    finally:
        if not keep:
            for f in (in_file, out_file):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick smoke test
    cfg = load_llm_config()
    if not is_wrapper_configured(cfg):
        print("call_llm.py: llm_wrapper.py not found next to this script.", file=sys.stderr)
        print("Place llm_wrapper.py in the same directory, or set wrapper_path.", file=sys.stderr)
        sys.exit(1)

    print(f"call_llm.py self-test: wrapper found at {cfg['wrapper_path']}")
    print("  (no actual LLM call made — use --verbose for details)")
    sys.exit(0)