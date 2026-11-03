"""
setup_data.py
─────────────
One-time data preparation script.
Run this ONCE before launching the Streamlit application:

    python setup_data.py

What it does:
  1. Creates the data/ directory.
  2. Downloads the Hetionet v1.0 nodes and edges files from GitHub.
  3. Filters the ~2.25 million edges down to the 7 types used by this application.
  4. Saves the filtered edge file as data/edges_filtered.tsv for fast loading.

After this script completes, you do not need an internet connection to run the app.
"""

import gzip
import os
import sys
import urllib.request
from pathlib import Path

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

NODES_FILE    = DATA_DIR / "hetionet-v1.0-nodes.tsv"
EDGES_GZ_FILE = DATA_DIR / "hetionet-v1.0-edges.sif.gz"
EDGES_FILTERED = DATA_DIR / "edges_filtered.tsv"

# ── Download URLs ───────────────────────────────────────────────────────────
NODES_URL = (
    "https://github.com/hetio/hetionet/raw/main/hetnet/tsv/hetionet-v1.0-nodes.tsv"
)
EDGES_URL = (
    "https://github.com/hetio/hetionet/raw/main/hetnet/tsv/hetionet-v1.0-edges.sif.gz"
)

# ── Edge types to keep ──────────────────────────────────────────────────────
# CbG  – Compound binds Gene            (drug molecular targets)
# CtD  – Compound treats Disease        (approved indications)
# CpD  – Compound palliates Disease     (approved indications)
# GaD  – Gene associates Disease        (disease–gene links, core repurposing)
# CcSE – Compound causes SideEffect     (side-effect profiles)
# GpPW – Gene participates Pathway      (pathway context)
# PCiC – PharmacologicClass includes Compound (drug class labels)
KEEP_METAEDGES = {"CbG", "CtD", "CpD", "GaD", "CcSE", "GpPW", "PCiC"}


def download_with_progress(url: str, dest: Path) -> None:
    """Download a file, showing a simple progress indicator."""
    print(f"  Downloading {dest.name} ...")

    def _report(block_count, block_size, total_size):
        downloaded = block_count * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 // total_size)
            bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
            print(f"\r    [{bar}] {pct:3d}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=_report)
    print()  # newline after progress bar


def main() -> None:
    print("=" * 60)
    print("  Intelligent Drug Repurposing System — Data Setup")
    print("=" * 60)

    # ── Step 1: Download nodes ──────────────────────────────────────────────
    print("\n[1/3] Nodes file")
    if NODES_FILE.exists():
        size_mb = NODES_FILE.stat().st_size / 1_048_576
        print(f"  Already present ({size_mb:.1f} MB). Skipping download.")
    else:
        download_with_progress(NODES_URL, NODES_FILE)

    # ── Step 2: Download edges ──────────────────────────────────────────────
    print("\n[2/3] Edges file (compressed, ~30 MB)")
    if EDGES_GZ_FILE.exists():
        size_mb = EDGES_GZ_FILE.stat().st_size / 1_048_576
        print(f"  Already present ({size_mb:.1f} MB). Skipping download.")
    else:
        download_with_progress(EDGES_URL, EDGES_GZ_FILE)

    # ── Step 3: Filter edges ────────────────────────────────────────────────
    print("\n[3/3] Filtering edges ...")

    if EDGES_FILTERED.exists():
        print("  Filtered file already exists. Re-generating to ensure correctness.")

    print("  Reading compressed edges file (this may take 30–60 seconds) ...")
    with gzip.open(EDGES_GZ_FILE, "rt", encoding="utf-8") as f:
        edges_df = pd.read_csv(
            f,
            sep="\t",
            header=None,
            names=["source", "metaedge", "target"],
        )

    total = len(edges_df)
    print(f"  Total edges in Hetionet: {total:,}")

    print("\n  All edge types and counts:")
    for metaedge, count in edges_df["metaedge"].value_counts().items():
        kept = "✓ kept" if metaedge in KEEP_METAEDGES else "  skip"
        print(f"    {kept}  {metaedge:<8}  {count:>9,}")

    filtered = edges_df[edges_df["metaedge"].isin(KEEP_METAEDGES)].copy()
    filtered.to_csv(EDGES_FILTERED, sep="\t", index=False)

    print(f"\n  Kept {len(filtered):,} edges ({len(KEEP_METAEDGES)} types).")
    print(f"  Saved to: {EDGES_FILTERED}")

    # ── Summary ─────────────────────────────────────────────────────────────
    nodes_df = pd.read_csv(NODES_FILE, sep="\t")
    print("\n" + "=" * 60)
    print("  Dataset summary")
    print("=" * 60)
    for kind, count in nodes_df["kind"].value_counts().items():
        print(f"  {kind:<25}  {count:>7,} nodes")
    print(f"\n  Total nodes  : {len(nodes_df):>7,}")
    print(f"  Kept edges   : {len(filtered):>7,}")
    print("=" * 60)
    print("\n  Setup complete!")
    print("  Run the application with:  streamlit run app.py")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n\nError during setup: {exc}")
        raise
