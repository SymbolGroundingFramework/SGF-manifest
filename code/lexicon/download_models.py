#!/usr/bin/env python3
"""
download_models.py

Pre-fetches the ONNX embedding models and the OpenSubtitles frequency
file so the actual pipeline run has no surprise downloads.

By default this downloads:

    Xenova/bge-small-en-v1.5      ~130 MB  (first-pass embeddings)
    Xenova/bge-large-en-v1.5      ~1.34 GB (production embeddings)
    OpenSubtitles 2018 en_full    ~30 MB   (lemma frequency rankings)

Total: ~1.5 GB.

Add --include-m3 to also fetch:

    Xenova/bge-m3                 ~2.2 GB  (cross-language embeddings)

Models cache to the standard HuggingFace location:
    Linux / Mac:  ~/.cache/huggingface/
    Windows:      %USERPROFILE%\\.cache\\huggingface\\

The frequency file caches to ./data/en_full.txt next to this script.

Usage:
    python download_models.py
    python download_models.py --include-m3
    python download_models.py --skip-frequency
    python download_models.py --skip-models
"""

import argparse
import sys
import time
import urllib.request
from pathlib import Path


MODELS = [
    {
        "repo": "Xenova/bge-small-en-v1.5",
        "tokenizer_repo": "BAAI/bge-small-en-v1.5",
        "model_file": "onnx/model.onnx",
        "size_label": "~130 MB",
        "purpose": "first-pass diagnostic embeddings (Stage 5)",
        "default": True,
    },
    {
        "repo": "Xenova/bge-large-en-v1.5",
        "tokenizer_repo": "BAAI/bge-large-en-v1.5",
        "model_file": "onnx/model.onnx",
        "size_label": "~1.34 GB",
        "purpose": "production embeddings (Stage 8)",
        "default": True,
    },
    {
        "repo": "Xenova/bge-m3",
        "tokenizer_repo": "BAAI/bge-m3",
        "model_file": "onnx/model.onnx",
        "model_data": "onnx/model.onnx_data",   # bge-m3 has a separate data file
        "size_label": "~2.2 GB",
        "purpose": "cross-language embeddings (optional)",
        "default": False,
    },
]


OPENSUBTITLES_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
    "master/content/2018/en/en_full.txt"
)


def download_model(spec):
    """Fetch one model + its tokenizer through huggingface_hub.

    Returns the local cache path of the model file.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub not installed.", file=sys.stderr)
        print("       Run `pip install -r requirements.txt` first.",
              file=sys.stderr)
        sys.exit(1)

    print()
    print(f"=== {spec['repo']}  ({spec['size_label']}, {spec['purpose']}) ===")

    t0 = time.time()
    model_path = hf_hub_download(
        repo_id=spec["repo"], filename=spec["model_file"]
    )
    print(f"  model:     {model_path}")

    if spec.get("model_data"):
        data_path = hf_hub_download(
            repo_id=spec["repo"], filename=spec["model_data"]
        )
        print(f"  data:      {data_path}")

    tok_path = hf_hub_download(
        repo_id=spec["tokenizer_repo"], filename="tokenizer.json"
    )
    print(f"  tokenizer: {tok_path}")

    elapsed = time.time() - t0
    print(f"  done in {elapsed:.1f}s")
    return model_path


def download_frequency_file(target_path):
    """Fetch the OpenSubtitles 2018 English unigram frequency file."""
    print()
    print(f"=== OpenSubtitles 2018 English unigram counts  (~30 MB) ===")
    print(f"  source: {OPENSUBTITLES_URL}")

    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        size_mb = target_path.stat().st_size / 1e6
        print(f"  already cached at {target_path} ({size_mb:.1f} MB); skipping")
        return target_path

    t0 = time.time()
    with urllib.request.urlopen(OPENSUBTITLES_URL) as r:
        data = r.read()
    target_path.write_bytes(data)
    elapsed = time.time() - t0
    size_mb = len(data) / 1e6
    print(f"  cached at {target_path} ({size_mb:.1f} MB) in {elapsed:.1f}s")
    return target_path


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--include-m3", action="store_true",
                   help="Also download Xenova/bge-m3 (~2.2 GB) for "
                        "cross-language embeddings")
    p.add_argument("--skip-models", action="store_true",
                   help="Skip ONNX model downloads")
    p.add_argument("--skip-frequency", action="store_true",
                   help="Skip OpenSubtitles frequency file download")
    args = p.parse_args()

    print("download_models.py -- pre-fetching all heavy assets")
    print("=" * 60)

    if not args.skip_models:
        for spec in MODELS:
            if spec["default"] or (args.include_m3 and spec["repo"].endswith("bge-m3")):
                download_model(spec)
    else:
        print("(skipping models per --skip-models)")

    if not args.skip_frequency:
        here = Path(__file__).resolve().parent
        download_frequency_file(here / "data" / "en_full.txt")
    else:
        print("(skipping frequency file per --skip-frequency)")

    print()
    print("=" * 60)
    print("All requested downloads complete.")
    print("You are now ready to run the pipeline -- see README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
