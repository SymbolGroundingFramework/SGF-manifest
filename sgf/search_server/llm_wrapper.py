#!/usr/bin/env python3
"""
llm_wrapper.py — Single-file LLM caller for OpenRouter (cloud) & Ollama (local).
================================================================================

PURPOSE
-------
Drop-in LLM wrapper: CLI or `import llm_wrapper`. Stdlib only (Python 3.8+).

QUICKSTART
----------
1. Edit the GLOBAL SETTINGS below (API key, URLs, default models).
2. Run:  python llm_wrapper.py --in prompt.txt --out reply.txt

GLOBAL SETTINGS (edit before use)
---------------------------------
OPENROUTER_URL   = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY   = "sk-or-v1-..."
OPENROUTER_MODEL = "deepseek/deepseek-v4-flash"

OPENROUTER_MODEL = "openai/gpt-oss-120b"

OLLAMA_URL       = "http://host:11434/api/generate"
OLLAMA_MODEL     = "qwen3.6:27b"

DEFAULT_SOURCE   = "cloud"          # "cloud" | "local"
DEFAULT_TIMEOUT  = 300              # seconds
MAX_RETRIES      = 3                # simple retry (429/5xx/network)
RETRY_DELAY      = 2                # seconds between retries
VERBOSE          = False            # set True to see status messages (--verbose flag)

CLI USAGE
---------
Required:  --in-file FILE   (aliases: --input-file, --in, --in_file)
           --out-file FILE  (aliases: --output-file, --out, --out_file)

Optional:
  --source / --zone / --provider   {cloud,openrouter,or | local,ollama,ol}
      Default: "cloud"
  --temp / --temperature           <float 0.0-2.0> or alias
      Aliases: very-low(0.1), low(0.3), medium/balanced(0.5), high(0.7), very-high(0.9)
      Invalid values silently fall back to provider default (None).
  --model                          Override model for this call
  --verbose, -v                    Enable status messages (off by default)

PROGRAMMATIC USE
----------------
import llm_wrapper as llm
text = llm.call_openrouter("Hello!", model="gpt-4o", temp=0.2)
text = llm.call_ollama("Hello!", model="llama3", temp=None)
temp_val = llm.parse_temperature("high")   # -> 0.7
src = llm.parse_source("ollama")           # -> "local"

DEPENDENCIES: stdlib only (argparse, json, pathlib, urllib, time, sys)
"""

# =====================================================================
# GLOBAL SETTINGS -- EDIT THESE
# =====================================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
OPENROUTER_MODEL = "deepseek/deepseek-v4-flash"

OLLAMA_URL = "http://192.168.12.160:11434/api/generate"
OLLAMA_MODEL = "qwen3.6:27b"

DEFAULT_SOURCE = "cloud"        # "cloud" or "local"
DEFAULT_TIMEOUT = 300           # seconds per request
MAX_RETRIES = 3                 # total attempts (simple linear retry)
RETRY_DELAY = 2                 # seconds between retries
VERBOSE = False                 # set True to see status messages (--verbose flag)

# =====================================================================
# TEMPERATURE PARSING (PUBLIC)
# =====================================================================

TEMP_ALIASES = {
    "very-low": 0.1, "very_low": 0.1, "vl": 0.1,
    "low": 0.3, "l": 0.3,
    "medium": 0.5, "med": 0.5, "balanced": 0.5, "m": 0.5, "b": 0.5,
    "high": 0.7, "h": 0.7,
    "very-high": 0.9, "very_high": 0.9, "vh": 0.9,
}


def parse_temperature(val: str | None) -> float | None:
    """
    Convert CLI string to float.
    Returns None if not provided or if value is unrecognised (uses provider default).
    Accepts aliases (very-low, low, medium, balanced, high, very-high) or numeric strings.
    """
    if val is None:
        return None
    val = val.strip().lower()
    if val in TEMP_ALIASES:
        return TEMP_ALIASES[val]
    try:
        f = float(val)
        if 0.0 <= f <= 2.0:
            return f
    except ValueError:
        pass
    # Invalid value -- silently use provider default
    if VERBOSE:
        print(f"[WARNING] Invalid temperature '{val}', using provider default.", file=sys.stderr)
    return None


# =====================================================================
# SOURCE PARSING (PUBLIC)
# =====================================================================

def parse_source(val: str) -> str:
    """Normalise 'cloud'/'openrouter'/'or' -> 'cloud', 'local'/'ollama'/'ol' -> 'local'."""
    v = val.strip().lower()
    if v in ("cloud", "openrouter", "or"):
        return "cloud"
    if v in ("local", "ollama", "ol"):
        return "local"
    raise ValueError(f"Invalid source '{val}'. Use cloud/openrouter or local/ollama.")


# =====================================================================
# I/O & HTTP INTERNALS
# =====================================================================

import json
import os
import sys
import time
from pathlib import Path
import urllib.error
import urllib.request


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig", errors="replace")


def _write_text(path: str, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> str:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _call_with_retry(url: str, payload: dict, headers: dict, timeout: int) -> str:
    """Simple retry: MAX_RETRIES attempts, RETRY_DELAY sleep on 429/5xx/net errors."""
    last_err = ""
    for attempt in range(MAX_RETRIES):
        try:
            return _post_json(url, payload, headers, timeout)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(last_err)
        except urllib.error.URLError as e:
            last_err = f"Network: {e.reason}"
        except Exception as e:
            last_err = f"Unexpected: {e}"
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
    raise RuntimeError(f"Failed after {MAX_RETRIES} attempts. Last error: {last_err}")


# =====================================================================
# PROVIDER IMPLEMENTATIONS (PUBLIC)
# =====================================================================

def call_openrouter(prompt: str, model: str, temp: float | None) -> str:
    """Call OpenRouter Chat Completions API. Returns assistant message content."""
    if not OPENROUTER_KEY or "YOUR" in OPENROUTER_KEY.upper():
        raise RuntimeError("OPENROUTER_KEY missing or placeholder in globals.")

    messages = [{"role": "user", "content": prompt}]

    payload = {"model": model, "messages": messages, "max_tokens": 16384}
    if temp is not None:
        payload["temperature"] = temp

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/local-llm-wrapper",
        "X-Title": "Local LLM Wrapper",
    }

    raw = _call_with_retry(OPENROUTER_URL, payload, headers, DEFAULT_TIMEOUT)
    data = json.loads(raw)
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def call_ollama(prompt: str, model: str, temp: float | None) -> str:
    """Call Ollama /api/generate. Returns response text."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": 8192}
    }
    if temp is not None:
        payload["options"]["temperature"] = temp

    headers = {"Content-Type": "application/json"}
    raw = _call_with_retry(OLLAMA_URL, payload, headers, DEFAULT_TIMEOUT)
    data = json.loads(raw)
    return data.get("response") or data.get("message", {}).get("content", "")


# =====================================================================
# CLI ENTRYPOINT
# =====================================================================

import argparse


class CleanArgParser(argparse.ArgumentParser):
    """Override error method to show only primary option names."""
    def error(self, message):
        if "the following arguments are required" in message:
            print(f"usage: {self.prog} [-h] --in-file IN_FILE --out-file OUT_FILE [--source SOURCE] [--temp TEMP] [--model MODEL] [--verbose]", file=sys.stderr)
            print(f"{self.prog}: error: the following arguments are required: --in-file, --out-file", file=sys.stderr)
        else:
            super().error(message)
        sys.exit(2)


def main():
    global VERBOSE

    parser = CleanArgParser(
        description="Single-file LLM Wrapper (OpenRouter + Ollama)",
        usage="llm_wrapper.py [-h] --in-file IN_FILE --out-file OUT_FILE [--source SOURCE] [--temp TEMP] [--model MODEL] [--verbose]",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # Required -- only primary alias in help text, but all aliases accepted
    parser.add_argument("--in-file", "--input-file", "--in", "--input_file", "--in_file",
                        required=True, dest="in_file",
                        help="Input prompt file (aliases: --input-file, --in, --in_file)")
    parser.add_argument("--out-file", "--output-file", "--out", "--output_file", "--out_file",
                        required=True, dest="out_file",
                        help="Output response file (aliases: --output-file, --out, --out_file)")

    # Optional
    parser.add_argument("--source", "--zone", "--provider",
                        default=DEFAULT_SOURCE, dest="source",
                        help=f"Source: cloud/openrouter or local/ollama (default: {DEFAULT_SOURCE})")
    parser.add_argument("--temp", "--temperature",
                        default=None, dest="temp",
                        help="Temperature: number (0.1) or alias (very-low, low, medium, high, very-high).\n"
                             "Invalid values silently use provider default. Omit for provider default.")
    parser.add_argument("--model",
                        default=None, dest="model",
                        help="Override model name (default: global setting for source)")
    parser.add_argument("--verbose", "-v",
                        action="store_true", dest="verbose",
                        help="Enable status messages (off by default)")

    args = parser.parse_args()
    if args.verbose:
        VERBOSE = True

    # Resolve settings
    try:
        source = parse_source(args.source)
        temperature = parse_temperature(args.temp)
        model = args.model or (OPENROUTER_MODEL if source == "cloud" else OLLAMA_MODEL)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Load prompt
    try:
        prompt = _read_text(args.in_file)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Dispatch
    if VERBOSE:
        print(f"-> Calling [{source.upper()}] model: {model} | temp: {temperature if temperature is not None else 'provider-default'}", file=sys.stderr)
    try:
        if source == "cloud":
            response = call_openrouter(prompt, model, temperature)
        else:
            response = call_ollama(prompt, model, temperature)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Save
    _write_text(args.out_file, response or "")
    if VERBOSE:
        print(f"Written to {args.out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
