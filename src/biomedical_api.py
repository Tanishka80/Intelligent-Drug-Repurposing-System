"""Small, cached clients for public biomedical sources used by the assistant.

Open Targets supplies entity search and curated target/indication associations.
NCBI PubMed E-utilities supplies publication metadata. API responses are kept
separate from Hetionet results so the UI can label their provenance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import requests
import streamlit as st

OPEN_TARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
PUBMED_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
REQUEST_TIMEOUT = 15
HEADERS = {"User-Agent": "DrugRepurposingResearchAssistant/1.0 (public biomedical research)"}


def _graphql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(
        OPEN_TARGETS_URL,
        json={"query": query, "variables": variables},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        messages = "; ".join(error.get("message", "GraphQL error") for error in payload["errors"])
        raise ValueError(messages)
    return payload.get("data") or {}


@st.cache_data(ttl=3600, show_spinner=False)
def search_opentargets(query: str, entity: str, limit: int = 8) -> Dict[str, Any]:
    """Search Open Targets for disease or drug names and available aliases."""
    entity_name = {"disease": "disease", "drug": "drug"}.get(entity)
    if not query.strip() or entity_name is None:
        return {"results": [], "error": None}
    gql = """
    query ($queryString: String!, $entityNames: [String!], $page: Pagination) {
      search(queryString: $queryString, entityNames: $entityNames, page: $page) {
        hits { id entity name description }
      }
    }
    """
    try:
        data = _graphql(gql, {
            "queryString": query.strip(),
            "entityNames": [entity_name],
            "page": {"index": 0, "size": max(1, min(int(limit), 20))},
        })
        hits = (data.get("search") or {}).get("hits") or []
        return {"results": hits, "error": None}
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {"results": [], "error": str(exc)}


@st.cache_data(ttl=3600, show_spinner=False)
def get_opentargets_disease(disease_id: str) -> Dict[str, Any]:
    """Retrieve disease description, aliases and associated target evidence."""
    gql = """
    query ($id: String!) {
      disease(efoId: $id) {
        id name description
        synonyms { terms relation }
        associatedTargets(page: {index: 0, size: 20}) {
          count rows { score target { id approvedSymbol approvedName } }
        }
                drugAndClinicalCandidates {
                    count
                    rows { maxClinicalStage drug { id name } }
                }
      }
    }
    """
    try:
        disease = _graphql(gql, {"id": disease_id}).get("disease")
        if not disease:
            return {"result": None, "error": None}
        aliases = []
        for group in disease.get("synonyms") or []:
            aliases.extend(group.get("terms") or [])
        associated = (disease.get("associatedTargets") or {}).get("rows") or []
        clinical_candidates = (
            disease.get("drugAndClinicalCandidates") or {}
        )
        candidate_rows = clinical_candidates.get("rows") or []
        return {
            "result": {
                "id": disease.get("id"),
                "name": disease.get("name"),
                "description": disease.get("description"),
                "aliases": list(dict.fromkeys(aliases))[:30],
                "targets": [
                    {
                        "id": row.get("target", {}).get("id"),
                        "symbol": row.get("target", {}).get("approvedSymbol"),
                        "name": row.get("target", {}).get("approvedName"),
                        "score": row.get("score"),
                    }
                    for row in associated
                ],
                "target_count": (disease.get("associatedTargets") or {}).get("count", 0),
                "clinical_candidate_count": clinical_candidates.get("count", 0),
                "clinical_candidates": [
                    {
                        "id": row.get("drug", {}).get("id"),
                        "name": row.get("drug", {}).get("name"),
                        "max_clinical_stage": row.get("maxClinicalStage"),
                    }
                    for row in candidate_rows
                    if row.get("drug")
                ][:20],
            },
            "error": None,
        }
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {"result": None, "error": str(exc)}


@st.cache_data(ttl=3600, show_spinner=False)
def get_opentargets_drug(chembl_id: str) -> Dict[str, Any]:
    """Retrieve a drug's Open Targets mechanisms, targets, names and indications."""
    gql = """
    query ($id: String!) {
      drug(chemblId: $id) {
        id name description
        tradeNames { label source }
        mechanismsOfAction {
          rows { mechanismOfAction targets { id approvedSymbol approvedName } }
        }
        indications { rows { disease { id name } } }
                drugWarnings {
                    warningType toxicityClass efoTerm description country year
                    references { id url source }
                }
      }
    }
    """
    try:
        drug = _graphql(gql, {"id": chembl_id}).get("drug")
        if not drug:
            return {"result": None, "error": None}
        mechanisms = (drug.get("mechanismsOfAction") or {}).get("rows") or []
        targets, mechanism_names = [], []
        for mechanism in mechanisms:
            if mechanism.get("mechanismOfAction"):
                mechanism_names.append(mechanism["mechanismOfAction"])
            targets.extend(mechanism.get("targets") or [])
        indications = (drug.get("indications") or {}).get("rows") or []
        warnings = drug.get("drugWarnings") or []
        return {
            "result": {
                "id": drug.get("id"),
                "name": drug.get("name"),
                "description": drug.get("description"),
                "trade_names": [item.get("label") for item in drug.get("tradeNames") or [] if item.get("label")],
                "mechanisms": list(dict.fromkeys(mechanism_names)),
                "targets": list({item.get("id"): item for item in targets if item.get("id")}.values()),
                "indications": [
                    row.get("disease", {}).get("name")
                    for row in indications if row.get("disease", {}).get("name")
                ],
                "warnings": warnings,
            },
            "error": None,
        }
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {"result": None, "error": str(exc)}


@st.cache_data(ttl=1800, show_spinner=False)
def search_pubmed(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search PubMed and return citation metadata with stable source links."""
    if not query.strip():
        return {"results": [], "error": None}
    try:
        response = requests.get(
            f"{PUBMED_EUTILS}/esearch.fcgi",
            params={"db": "pubmed", "term": query.strip(), "retmode": "json", "retmax": max(1, min(int(limit), 10))},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        ids = response.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return {"results": [], "error": None}
        summary = requests.get(
            f"{PUBMED_EUTILS}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        summary.raise_for_status()
        result = summary.json().get("result", {})
        items = []
        for pmid in result.get("uids", ids):
            citation = result.get(pmid, {})
            items.append({
                "pmid": pmid,
                "title": citation.get("title") or "Title unavailable",
                "journal": citation.get("fulljournalname") or citation.get("source") or "",
                "date": citation.get("pubdate") or "",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })
        return {"results": items, "error": None}
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {"results": [], "error": str(exc)}


def pubmed_pair_query(drug_name: str, disease_name: str) -> str:
    """Create a conservative PubMed query for a drug/disease evidence search."""
    return f'("{drug_name}"[Title/Abstract]) AND ("{disease_name}"[Title/Abstract])'
