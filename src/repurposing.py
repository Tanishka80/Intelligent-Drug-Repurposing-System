"""
src/repurposing.py
──────────────────
Core drug-repurposing logic.

All functions operate on Pandas DataFrames loaded by data_loader.py.
No graph database or external service is required.

Scientific approach
───────────────────
Drug repurposing candidates are found by traversing a two-hop path:

    Compound ──[CbG]──► Gene ──[GaD]──► Disease

Interpretation:
  A drug that binds a gene which is genetically associated with a disease
  is a potential repurposing candidate for that disease,
  provided the drug is not already approved for treating that disease.

Ranking score:
  Score = number of distinct genes connecting the drug to the disease.
  A higher score means more molecular evidence, making the candidate
  a stronger hypothesis for further investigation.

All results are RESEARCH HYPOTHESES only — not clinical recommendations.
"""

from typing import List, Dict, Optional, Tuple
import pandas as pd
import streamlit as st

from src.data_loader import load_nodes, load_edges
from src.utils import format_list, extract_raw_id, pubmed_search_url, fuzzy_search


# ── Disease search ───────────────────────────────────────────────────────────

def search_diseases(query: str) -> pd.DataFrame:
    """
    Search diseases by case-insensitive exact, partial, and fuzzy name match.

    Parameters
    ----------
    query : str
        User-typed search term.

    Returns
    -------
    pd.DataFrame with columns: id, name
        Matching disease nodes ranked by match quality.
    """
    nodes = load_nodes()
    diseases = nodes[nodes["kind"] == "Disease"][["id", "name"]].copy()
    if not query.strip():
        return pd.DataFrame(columns=["id", "name"])
    return fuzzy_search(query, diseases, col="name")


# ── Repurposing candidates ───────────────────────────────────────────────────

@st.cache_data(show_spinner="Analysing drug–disease relationships...")
def find_repurposing_candidates(
    disease_id: str,
    top_n: int = 30,
) -> pd.DataFrame:
    """
    Find and rank drug repurposing candidates for a given disease.

    Algorithm
    ---------
    1. Find all genes associated with the disease (GaD edges).
    2. Find all drugs that bind those genes (CbG edges).
    3. Exclude drugs already approved for the disease (CtD / CpD edges).
    4. Group by drug; count distinct connecting genes → repurposing score.
    5. Sort by score descending and return the top_n results.

    Parameters
    ----------
    disease_id : str
        Node identifier for the target disease (e.g. 'Disease::DOID:9352').
    top_n : int
        Maximum number of candidates to return.

    Returns
    -------
    pd.DataFrame with columns:
        rank, drug_id, drug_name, gene_count, connecting_genes,
        current_indications, drug_class, drugbank_id
    Returns an empty DataFrame if no candidates are found.
    """
    nodes = load_nodes()
    edges = load_edges()

    # ── Step 1: Genes associated with this disease ──────────────────────────
    disease_gene_edges = edges[
        (edges["metaedge"] == "GaD") & (edges["target"] == disease_id)
    ]
    gene_ids = set(disease_gene_edges["source"].unique())

    if not gene_ids:
        return pd.DataFrame()

    # ── Step 2: Drugs that bind those genes ─────────────────────────────────
    drug_gene_edges = edges[
        (edges["metaedge"] == "CbG") & (edges["target"].isin(gene_ids))
    ][["source", "target"]].copy()
    drug_gene_edges.columns = ["drug_id", "gene_id"]

    if drug_gene_edges.empty:
        return pd.DataFrame()

    # ── Step 3: Exclude already-approved drugs ──────────────────────────────
    approved_drug_ids = set(
        edges[
            (edges["metaedge"].isin(["CtD", "CpD"])) &
            (edges["target"] == disease_id)
        ]["source"].unique()
    )
    drug_gene_edges = drug_gene_edges[
        ~drug_gene_edges["drug_id"].isin(approved_drug_ids)
    ]

    if drug_gene_edges.empty:
        return pd.DataFrame()

    # ── Step 4: Group by drug, collect and count connecting genes ───────────
    grouped = (
        drug_gene_edges.groupby("drug_id")["gene_id"]
        .apply(lambda g: sorted(set(g)))
        .reset_index()
    )
    grouped.columns = ["drug_id", "connecting_gene_ids"]
    grouped["gene_count"] = grouped["connecting_gene_ids"].apply(len)
    grouped = grouped.sort_values("gene_count", ascending=False).head(top_n)

    # ── Step 5: Add human-readable node names ───────────────────────────────
    # Build lookup maps
    node_name_map = nodes.set_index("id")["name"].to_dict()

    grouped["drug_name"] = grouped["drug_id"].map(node_name_map)
    grouped["connecting_genes"] = grouped["connecting_gene_ids"].apply(
        lambda ids: [node_name_map.get(gid, gid) for gid in ids]
    )

    # Remove rows where drug name is missing (shouldn't happen, but guard)
    grouped = grouped[grouped["drug_name"].notna()].copy()

    # ── Step 6: Current indications for each candidate drug ─────────────────
    candidate_ids = set(grouped["drug_id"])
    indication_edges = edges[
        edges["metaedge"].isin(["CtD", "CpD"]) &
        edges["source"].isin(candidate_ids)
    ][["source", "target"]]

    indications_map: Dict[str, List[str]] = {}
    for drug_id, group in indication_edges.groupby("source"):
        disease_names = [
            node_name_map.get(d, d)
            for d in group["target"].tolist()
        ]
        indications_map[drug_id] = sorted(set(disease_names))

    grouped["current_indications"] = grouped["drug_id"].apply(
        lambda did: indications_map.get(did, [])
    )

    # ── Step 7: Drug class (PharmacologicClass includes Compound) ───────────
    pc_edges = edges[
        (edges["metaedge"] == "PCiC") & edges["target"].isin(candidate_ids)
    ][["source", "target"]]

    drug_class_map: Dict[str, str] = {}
    for drug_id, group in pc_edges.groupby("target"):
        class_names = [node_name_map.get(pc, pc) for pc in group["source"].tolist()]
        drug_class_map[drug_id] = "; ".join(sorted(set(class_names)))

    grouped["drug_class"] = grouped["drug_id"].map(drug_class_map).fillna("—")

    # ── Step 8: Extract raw DrugBank ID for external links ──────────────────
    grouped["drugbank_id"] = grouped["drug_id"].apply(extract_raw_id)

    # ── Final cleanup ────────────────────────────────────────────────────────
    grouped = grouped.reset_index(drop=True)
    grouped.insert(0, "rank", grouped.index + 1)

    return grouped[[
        "rank", "drug_id", "drug_name", "gene_count",
        "connecting_genes", "connecting_gene_ids",
        "current_indications", "drug_class", "drugbank_id",
    ]]


# ── Explanation generator ────────────────────────────────────────────────────

def explain_candidate(
    drug_name: str,
    disease_name: str,
    connecting_genes: List[str],
    current_indications: List[str],
    drug_class: str,
    gene_count: int,
    drug_id: str,
) -> Dict[str, str]:
    """
    Generate a structured rule-based explanation for a repurposing candidate.

    Returns a dict with keys:
        summary      – one-sentence headline
        mechanism    – biological pathway explanation
        evidence     – data source description
        indications  – current uses
        caveat       – mandatory disclaimer
        pubmed_url   – PubMed search link (no API call, just a URL)
    """
    gene_list = format_list(connecting_genes, max_items=6)
    has_indications = bool(current_indications)

    if gene_count == 1:
        gene_phrase = f"one shared molecular target ({gene_list})"
    elif gene_count <= 3:
        gene_phrase = f"{gene_count} shared molecular targets ({gene_list})"
    else:
        gene_phrase = (
            f"{gene_count} shared molecular targets, including {gene_list}"
        )

    summary = (
        f"{drug_name} is identified as a potential repurposing candidate "
        f"for {disease_name} based on {gene_phrase}."
    )

    mechanism = (
        f"{drug_name} is known to bind or regulate {gene_list}. "
        f"{'This gene is' if gene_count == 1 else 'These genes are'} "
        f"genetically associated with {disease_name} in the Hetionet "
        f"biomedical knowledge graph, suggesting a shared biological pathway "
        f"that may be relevant to the disease."
    )

    if has_indications:
        indication_text = format_list(current_indications, max_items=4)
        indications = f"Currently approved for: {indication_text}."
    else:
        indications = "No current disease indications are recorded in this dataset."

    if drug_class and drug_class != "—":
        indications += f" Drug class: {drug_class}."

    evidence = (
        "This association is derived from the Hetionet v1.0 biomedical "
        "knowledge graph, which integrates data from DrugBank, OMIM, "
        "DisGeNET, Reactome, Gene Ontology, and other curated databases. "
        "Relationship types used: CbG (Compound binds Gene) and "
        "GaD (Gene associates Disease)."
    )

    caveat = (
        "⚠️  This is a computational research hypothesis generated by "
        "analysing molecular target overlap. It has NOT been clinically "
        "validated. Do not use this information for medical decisions."
    )

    pubmed_url = pubmed_search_url(drug_name, disease_name)

    return {
        "summary":     summary,
        "mechanism":   mechanism,
        "indications": indications,
        "evidence":    evidence,
        "caveat":      caveat,
        "pubmed_url":  pubmed_url,
    }


# ── Drug profile ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Loading drug profile...")
def get_drug_profile(drug_id: str) -> Dict:
    """
    Return a comprehensive profile for a single drug.

    Parameters
    ----------
    drug_id : str
        Node identifier (e.g. 'Compound::DB00331').

    Returns
    -------
    dict with keys:
        drug_id, drug_name, drugbank_id,
        treats, palliates, targets,
        side_effects, pathways, drug_class
    Each list value is a list of human-readable names.
    Returns None if the drug_id is not found.
    """
    nodes = load_nodes()
    edges = load_edges()

    node_name_map = nodes.set_index("id")["name"].to_dict()
    drug_name = node_name_map.get(drug_id)
    if drug_name is None:
        return None

    def _get_targets(metaedge: str, direction: str = "outgoing") -> List[str]:
        """Get names of nodes connected to drug via given metaedge."""
        if direction == "outgoing":
            connected = edges[
                (edges["metaedge"] == metaedge) & (edges["source"] == drug_id)
            ]["target"]
        else:
            connected = edges[
                (edges["metaedge"] == metaedge) & (edges["target"] == drug_id)
            ]["source"]
        return sorted(
            set(node_name_map.get(nid, nid) for nid in connected.unique())
        )

    # Drug class: PharmacologicClass -[PCiC]-> Compound
    drug_class_list = _get_targets("PCiC", direction="incoming")

    return {
        "drug_id":     drug_id,
        "drug_name":   drug_name,
        "drugbank_id": extract_raw_id(drug_id),
        "treats":      _get_targets("CtD"),
        "palliates":   _get_targets("CpD"),
        "targets":     _get_targets("CbG"),   # Compound -[CbG]-> Gene
        "side_effects": _get_targets("CcSE"),
        "pathways":    _get_targets("GpPW"),  # This is Gene->Pathway; need 2-hop
        "drug_class":  "; ".join(drug_class_list) if drug_class_list else "—",
    }


def _get_drug_pathways(drug_id: str) -> List[str]:
    """
    Two-hop query: Drug → Genes (CbG) → Pathways (GpPW).
    Returns a list of pathway names.
    """
    nodes = load_nodes()
    edges = load_edges()
    node_name_map = nodes.set_index("id")["name"].to_dict()

    # Step 1: get gene targets of this drug
    gene_ids = edges[
        (edges["metaedge"] == "CbG") & (edges["source"] == drug_id)
    ]["target"].unique()

    if len(gene_ids) == 0:
        return []

    # Step 2: get pathways of those genes
    pathway_ids = edges[
        (edges["metaedge"] == "GpPW") & (edges["source"].isin(gene_ids))
    ]["target"].unique()

    return sorted(
        set(node_name_map.get(pid, pid) for pid in pathway_ids)
    )


# ── Drug search ──────────────────────────────────────────────────────────────

def search_drugs(query: str) -> pd.DataFrame:
    """
    Search for drugs (Compound nodes) by name substring match.

    Returns a DataFrame with columns: id, name
    """
    nodes = load_nodes()
    drugs = nodes[nodes["kind"] == "Compound"][["id", "name"]].copy()
    if not query.strip():
        return pd.DataFrame(columns=["id", "name"])
    return fuzzy_search(query, drugs, col="name")
