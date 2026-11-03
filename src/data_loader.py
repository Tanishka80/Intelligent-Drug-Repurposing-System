"""
src/data_loader.py
──────────────────
Loads Hetionet v1.0 data files into Pandas DataFrames.

The @st.cache_data decorator makes Streamlit cache the DataFrames in memory
after the first load, so subsequent page navigations are instant.

Data files are expected in the data/ directory (created by setup_data.py).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

# ── File paths ──────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
DATA_DIR   = BASE_DIR / "data"
NODES_FILE = DATA_DIR / "hetionet-v1.0-nodes.tsv"
EDGES_FILE = DATA_DIR / "edges_filtered.tsv"


def _check_data_files() -> None:
    """Raise a clear error if data files are missing."""
    if not NODES_FILE.exists() or not EDGES_FILE.exists():
        raise FileNotFoundError(
            "Data files not found in the data/ directory.\n"
            "Please run setup first:\n\n"
            "    python setup_data.py\n"
        )


@st.cache_data(show_spinner="Loading node data...")
def load_nodes() -> pd.DataFrame:
    """
    Load all Hetionet nodes.

    Returns a DataFrame with columns:
        id   – unique node identifier (e.g. 'Compound::DB00331')
        name – human-readable name    (e.g. 'Metformin')
        kind – node type              (e.g. 'Compound', 'Gene', 'Disease')
    """
    _check_data_files()
    df = pd.read_csv(NODES_FILE, sep="\t", dtype=str)
    df.columns = df.columns.str.strip()
    return df


@st.cache_data(show_spinner="Loading relationship data...")
def load_edges() -> pd.DataFrame:
    """
    Load pre-filtered Hetionet edges.

    Returns a DataFrame with columns:
        source   – source node identifier
        metaedge – relationship type code (e.g. 'CbG', 'GaD')
        target   – target node identifier
    """
    _check_data_files()
    df = pd.read_csv(EDGES_FILE, sep="\t", dtype=str)
    df.columns = df.columns.str.strip()
    return df


@st.cache_data(show_spinner=False)
def get_dataset_stats() -> dict:
    """
    Return summary statistics for the home page.

    Returns a dict with keys:
        n_drugs, n_diseases, n_genes, n_side_effects,
        n_known_treatments, n_edges_total
    """
    nodes = load_nodes()
    edges = load_edges()

    kind_counts = nodes.groupby("kind").size()

    return {
        "n_drugs":           int(kind_counts.get("Compound",         0)),
        "n_diseases":        int(kind_counts.get("Disease",           0)),
        "n_genes":           int(kind_counts.get("Gene",              0)),
        "n_side_effects":    int(kind_counts.get("Side Effect",       0)),
        "n_pathways":        int(kind_counts.get("Pathway",           0)),
        "n_known_treatments": int(
            len(edges[edges["metaedge"].isin(["CtD", "CpD"])])
        ),
        "n_edges_total":     int(len(edges)),
    }
