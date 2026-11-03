"""
src/utils.py
────────────
Shared helper functions used across the application.
No Streamlit-specific code here — these are plain Python utilities.
"""

from typing import List, Optional
from difflib import SequenceMatcher
import re
import pandas as pd


# ── Text search ─────────────────────────────────────────────────────────────

def fuzzy_search(query: str, df: pd.DataFrame, col: str = "name") -> pd.DataFrame:
    """
    Case-insensitive exact, substring, and typo-tolerant search on a column.

    Parameters
    ----------
    query : str
        The search term entered by the user.
    df : pd.DataFrame
        DataFrame to search.
    col : str
        Column name to search within (default: 'name').

    Returns
    -------
    pd.DataFrame
        Matching rows with the original columns, ranked by match quality.
        A small number of fuzzy suggestions are included when substring
        matching alone does not provide enough choices.
    """
    q = query.strip().casefold()
    if not q:
        return df.iloc[0:0]  # empty DataFrame with same columns

    def normalize(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()

    names = df[col].fillna("").astype(str)
    normalized_query = normalize(q)
    if not normalized_query:
        return df.iloc[0:0]
    normalized_names = names.map(normalize)
    literal_mask = names.str.casefold().str.contains(re.escape(q), na=False)
    normalized_mask = normalized_names.str.contains(
        re.escape(normalized_query), na=False
    )
    matched = df[literal_mask | normalized_mask].copy()

    # Keep common typos and near-name queries useful without requiring an
    # additional fuzzy-matching dependency. Avoid fuzzy expansion for very
    # short queries, where it would produce noisy suggestions.
    if len(matched) < 8 and len(normalized_query) >= 4:
        matched_ids = set(matched.index)
        scores = []
        query_tokens = set(normalized_query.split())
        for index, name in normalized_names.items():
            if index in matched_ids or not name:
                continue
            name_tokens = set(name.split())
            score = max(
                SequenceMatcher(None, normalized_query, name).ratio(),
                max(
                    (SequenceMatcher(None, normalized_query, token).ratio() for token in name_tokens),
                    default=0.0,
                ),
            )
            if query_tokens and query_tokens.issubset(name_tokens):
                score = max(score, 0.88)
            if score >= 0.82:
                scores.append((score, index))
        scores.sort(key=lambda item: (-item[0], str(names.loc[item[1]]).casefold()))
        if scores:
            fuzzy_rows = df.loc[[index for _, index in scores[:8]]]
            matched = pd.concat([matched, fuzzy_rows]).drop_duplicates()

    # Rank exact names, prefixes, substrings, then fuzzy suggestions. Keep
    # match scores internal so existing callers retain their data contract.
    score_by_index = {}
    for index in matched.index:
        name = normalize(names.loc[index])
        if name == normalized_query:
            score = 1.0
        elif name.startswith(normalized_query):
            score = 0.96
        elif normalized_query in name:
            score = 0.90
        else:
            score = max(
                SequenceMatcher(None, normalized_query, name).ratio(),
                max(
                    (SequenceMatcher(None, normalized_query, token).ratio() for token in name.split()),
                    default=0.0,
                ),
            )
        score_by_index[index] = score
    matched["__match_score"] = [score_by_index[index] for index in matched.index]
    matched["__sort_name"] = matched[col].fillna("").astype(str).str.casefold()
    matched = matched.sort_values(
        ["__match_score", "__sort_name"], ascending=[False, True]
    ).head(50)
    return matched.drop(columns=["__match_score", "__sort_name"]).reset_index(drop=True)


# ── List formatting ──────────────────────────────────────────────────────────

def format_list(
    items: List[str],
    max_items: int = 8,
    separator: str = ", ",
    overflow_suffix: bool = True,
) -> str:
    """
    Join a list of strings, truncating with '(+N more)' if too long.

    Examples
    --------
    >>> format_list(['A', 'B', 'C', 'D'], max_items=3)
    'A, B, C (+1 more)'
    >>> format_list(['A', 'B'], max_items=5)
    'A, B'
    """
    if not items:
        return "None"
    visible = items[:max_items]
    remainder = len(items) - len(visible)
    result = separator.join(visible)
    if overflow_suffix and remainder > 0:
        result += f" (+{remainder} more)"
    return result


def format_list_lines(items: List[str], max_items: int = 10) -> str:
    """
    Format a list as a bullet-point string (for display in markdown).
    """
    if not items:
        return "_None found_"
    visible = items[:max_items]
    remainder = len(items) - len(visible)
    lines = ["• " + item for item in visible]
    if remainder > 0:
        lines.append(f"_... and {remainder} more_")
    return "\n".join(lines)


# ── External links ───────────────────────────────────────────────────────────

def drugbank_url(identifier: str) -> Optional[str]:
    """
    Return a DrugBank URL for a compound node identifier.

    Parameters
    ----------
    identifier : str
        Node identifier in the form 'Compound::DB00331'.

    Returns
    -------
    str or None
        URL string, or None if identifier format is unexpected.
    """
    if not isinstance(identifier, str):
        return None
    parts = identifier.split("::")
    if len(parts) == 2 and parts[1].startswith("DB"):
        return f"https://www.drugbank.ca/drugs/{parts[1]}"
    return None


def disease_ontology_url(identifier: str) -> Optional[str]:
    """
    Return a Disease Ontology URL for a disease node identifier.

    Parameters
    ----------
    identifier : str
        Node identifier in the form 'Disease::DOID:9352'.

    Returns
    -------
    str or None
    """
    if not isinstance(identifier, str):
        return None
    parts = identifier.split("::")
    if len(parts) == 2 and parts[1].startswith("DOID:"):
        doid = parts[1].replace("DOID:", "")
        return f"https://disease-ontology.org/term/DOID:{doid}"
    return None


def pubmed_search_url(drug_name: str, disease_name: str) -> str:
    """
    Return a PubMed search URL for a drug–disease pair.
    Opens directly in PubMed (no API required).
    """
    import urllib.parse
    query = urllib.parse.quote(f'"{drug_name}" AND "{disease_name}" AND repurposing')
    return f"https://pubmed.ncbi.nlm.nih.gov/?term={query}"


# ── ID helpers ───────────────────────────────────────────────────────────────

def extract_raw_id(node_id: str) -> str:
    """
    Extract the raw identifier from a Hetionet node ID.

    Examples
    --------
    >>> extract_raw_id('Compound::DB00331')
    'DB00331'
    >>> extract_raw_id('Disease::DOID:9352')
    'DOID:9352'
    """
    if not isinstance(node_id, str):
        return str(node_id)
    parts = node_id.split("::", 1)
    return parts[1] if len(parts) == 2 else node_id
