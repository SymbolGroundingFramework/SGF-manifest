#!/usr/bin/env python3
"""
llm_wrapper.py  --  the adapter the SGF lexicon pipeline calls.

The pipeline (Stages 6, 10, 11) always invokes this file by name:

    python llm_wrapper.py --in-file PROMPT --out-file RESPONSE [--tier ...] [--temp ...]

We ship this file as a convenience. It is a thin, editable adapter.
Make it call your LLM however you want. Two common ways below; pick one,
delete or ignore the other.

  OPTION A -- DELEGATE to your existing LLM script.
              You already have an LLM-calling script that works. Point
              this adapter at it and you're done. Edit the path on the
              line marked OPTION A below.

  OPTION B -- DIRECT call.
              You don't have an existing script (or you want a
              project-local copy). Replace the marked block with your
              own code that turns a prompt string into a response
              string.

Either way works. The contract the pipeline depends on is:

    1. Read the full prompt text from --in-file.
    2. Send it to your LLM however you want.
    3. Write the full response text to --out-file.
    4. Exit 0 on success, non-zero on failure.

Optional flags the pipeline may pass (you can honor or ignore):
    --tier flash       (cheap / fast model preferred)
    --tier reasoning   (heavy model preferred for hard calls)
    --temp 0.0         (or some other float)

Self-test (run any time to verify the wiring):

    python llm_wrapper.py --self-test
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


# =========================================================================
# OPTION A -- delegate to your existing LLM script.
# Edit the path below and you're done.
# =========================================================================

USE_OPTION_A = False        # flip to True to use this path
EXISTING_LLM_SCRIPT = r"C:\path\to\your_existing_llm_wrapper.py"


def call_via_existing_script(args):
    """Forward the same flags to your existing script as a subprocess."""
    script = Path(EXISTING_LLM_SCRIPT).expanduser()
    if not script.exists():
        print(
            f"ERROR: EXISTING_LLM_SCRIPT does not exist:\n"
            f"       {script}\n"
            f"\n"
            f"Edit llm_wrapper.py and update the EXISTING_LLM_SCRIPT path,\n"
            f"or flip USE_OPTION_A to False and use Option B below.",
            file=sys.stderr,
        )
        sys.exit(2)

    cmd = [sys.executable, str(script),
           "--in-file", args.in_file,
           "--out-file", args.out_file]
    if args.tier:
        cmd += ["--tier", args.tier]
    if args.temp is not None:
        cmd += ["--temp", str(args.temp)]

    return subprocess.run(cmd).returncode


# =========================================================================
# OPTION B -- direct call to your LLM.
# Replace the body of call_my_llm() with your own code.
# =========================================================================

def call_my_llm(prompt, tier=None, temp=None):
    """
    Turn the prompt string into a response string. Replace this body.

    Inputs:
        prompt: str  -- the full prompt text from --in-file
        tier:   str or None -- 'flash' / 'reasoning' / None
        temp:   float or None

    Return: str -- the full response text to be written to --out-file
    """
    raise NotImplementedError(
        "llm_wrapper.py: you have not configured the adapter yet.\n"
        "Either set USE_OPTION_A = True and point EXISTING_LLM_SCRIPT at\n"
        "your existing LLM script, OR replace the body of call_my_llm()\n"
        "with code that calls your LLM. See the docstring at the top."
    )


# =========================================================================
# Argument parsing + driver. You shouldn't need to edit below this line.
# =========================================================================

def parse_args(argv):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--in-file")
    p.add_argument("--out-file")
    p.add_argument("--tier", default=None)
    p.add_argument("--temp", type=float, default=None)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    args, _unknown = p.parse_known_args(argv)
    return args


def run_normal(args):
    """Normal pipeline invocation: prompt -> response."""
    if not args.in_file or not args.out_file:
        print("ERROR: both --in-file and --out-file are required.",
              file=sys.stderr)
        return 2

    if USE_OPTION_A:
        return call_via_existing_script(args)

    # Option B path: read prompt, call user's function, write response.
    prompt = Path(args.in_file).read_text(encoding="utf-8")
    response = call_my_llm(prompt, tier=args.tier, temp=args.temp)
    if not isinstance(response, str):
        print(f"ERROR: call_my_llm() returned {type(response).__name__}; "
              f"expected str.", file=sys.stderr)
        return 3
    Path(args.out_file).write_text(response, encoding="utf-8")
    return 0


def run_self_test():
    """Send a one-word test prompt through and report PASS / FAIL."""
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "prompt.txt"
        out_path = Path(td) / "response.txt"
        in_path.write_text("Reply with the single word: OK\n",
                           encoding="utf-8")

        class _A:
            in_file = str(in_path)
            out_file = str(out_path)
            tier = "flash"
            temp = 0.0

        try:
            rc = run_normal(_A())
        except NotImplementedError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1

        if rc != 0:
            print(f"FAIL: adapter exited with status {rc}", file=sys.stderr)
            return rc
        if not out_path.exists():
            print("FAIL: adapter exited 0 but did not write --out-file",
                  file=sys.stderr)
            return 4

        response = out_path.read_text(encoding="utf-8").strip()
        if not response:
            print("FAIL: adapter wrote an empty response", file=sys.stderr)
            return 5

        snippet = response[:200] + (" ..." if len(response) > 200 else "")
        print(f"response: {snippet!r}")
        print()
        print("PASS: adapter is wired up correctly.")
        return 0


def main():
    args = parse_args(sys.argv[1:])
    if args.help:
        print(__doc__)
        return 0
    if args.self_test:
        return run_self_test()
    return run_normal(args)


if __name__ == "__main__":
    sys.exit(main())
