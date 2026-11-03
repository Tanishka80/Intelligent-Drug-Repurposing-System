"""
pages/2_Drug_Profile.py
───────────────────────
View a comprehensive profile for any drug in the dataset.

Displays:
  - Molecular targets (genes the drug binds)
  - Diseases it currently treats or palliates
  - Known side effects
  - Biological pathways (via gene targets)
  - Drug class and external references
"""

import streamlit as st
import pandas as pd

from src.repurposing import search_drugs, get_drug_profile, _get_drug_pathways
from src.biomedical_api import get_opentargets_drug, search_opentargets, search_pubmed
from src.utils import format_list, format_list_lines, drugbank_url, extract_raw_id

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Drug Profile · Drug Repurposing",
    page_icon="💊",
    layout="wide",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.page-header {
    padding: 24px 0 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 24px;
}
.page-title { font-size: 1.8rem; font-weight: 700; color: #F0F2F6; margin: 0; }
.page-desc  { font-size: 0.9rem; color: #9EAAB8; margin: 6px 0 0 0; }

.profile-card {
    background: #1A1F2E;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 20px 22px;
    height: 100%;
}
.card-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: #9EAAB8;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    margin: 0 0 12px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.drug-hero {
    background: linear-gradient(135deg, #0D1B2A 0%, #1A2E3B 100%);
    border: 1px solid rgba(0, 201, 167, 0.25);
    border-radius: 14px;
    padding: 28px 32px;
    margin-bottom: 24px;
}
.drug-title {
    font-size: 2rem;
    font-weight: 700;
    color: #F0F2F6;
    margin: 0 0 6px 0;
}
.drug-id {
    font-size: 0.85rem;
    color: #6B7A8D;
    font-family: monospace;
    margin: 0 0 8px 0;
}
.drug-class-badge {
    display: inline-block;
    background: rgba(0, 201, 167, 0.12);
    color: #00C9A7;
    border: 1px solid rgba(0, 201, 167, 0.3);
    border-radius: 16px;
    padding: 3px 14px;
    font-size: 0.8rem;
    font-weight: 600;
}
.list-item {
    font-size: 0.85rem;
    color: #C5CDD9;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    line-height: 1.5;
}
.list-item:last-child { border-bottom: none; }
.empty-label {
    font-size: 0.82rem;
    color: #4A5568;
    font-style: italic;
    padding: 8px 0;
}
.count-badge {
    display: inline-block;
    background: rgba(255,255,255,0.07);
    color: #9EAAB8;
    border-radius: 10px;
    padding: 1px 8px;
    font-size: 0.72rem;
    margin-left: 6px;
    vertical-align: middle;
}
.warning-box {
    background: rgba(255, 193, 7, 0.06);
    border: 1px solid rgba(255, 193, 7, 0.28);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.82rem;
    color: #C9A227;
    margin-top: 16px;
}
.no-results {
    text-align: center;
    padding: 48px 0;
    color: #6B7A8D;
    font-size: 0.95rem;
}
</style>
""", unsafe_allow_html=True)


def show_live_drug_evidence(query: str) -> bool:
    """Show live Open Targets and PubMed records for a medicine search."""
    found_evidence = False
    with st.spinner("Searching Open Targets for generic and trade-name matches…"):
        matches = search_opentargets(query, "drug")

    if matches["error"]:
        st.warning(f"Open Targets is temporarily unavailable: {matches['error']}")
    elif matches["results"]:
        hits = matches["results"]
        exact_indices = [
            index for index, hit in enumerate(hits)
            if hit.get("name", "").casefold() == query.casefold()
        ]
        default_index = exact_indices[0] if exact_indices else 0
        if len(hits) > 1:
            labels = [f"{hit.get('name', 'Unnamed medicine')} — {hit.get('id')}" for hit in hits]
            selected = st.selectbox(
                "Choose the matching Open Targets medicine",
                labels,
                index=default_index,
                key="drug_profile_external_choice",
            )
            hit = hits[labels.index(selected)]
        else:
            hit = hits[0]

        with st.spinner(f"Loading live profile for {hit.get('name', query)}…"):
            profile_response = get_opentargets_drug(hit["id"])
        if profile_response["error"]:
            st.warning(f"Open Targets medicine details could not be loaded: {profile_response['error']}")
        elif profile_response["result"]:
            found_evidence = True
            profile = profile_response["result"]
            st.markdown(
                f"**Source: Open Targets Platform** · "
                f"[{profile['name']} — {profile['id']}]("
                f"https://platform.opentargets.org/drug/{profile['id']})"
            )
            if profile.get("description"):
                st.write(profile["description"])
            if profile.get("trade_names"):
                st.markdown("**Generic/trade-name aliases:** " + format_list(profile["trade_names"], max_items=15))
            if profile.get("mechanisms"):
                st.markdown("**Reported mechanisms:** " + format_list(profile["mechanisms"], max_items=12))
            targets = profile.get("targets") or []
            if targets:
                st.markdown("**Mechanism-linked targets:**")
                st.dataframe(pd.DataFrame([
                    {
                        "Target": target.get("approvedSymbol") or target.get("approvedName") or target.get("id"),
                        "Ensembl ID": target.get("id"),
                    }
                    for target in targets
                ]), use_container_width=True, hide_index=True)
            else:
                st.info("Open Targets returned no mechanism-linked targets for this record.")
            if profile.get("indications"):
                st.markdown("**Disease indications listed by Open Targets:** " + format_list(profile["indications"], max_items=25))
            else:
                st.info("Open Targets returned no disease indications for this medicine.")
            warnings = profile.get("warnings") or []
            if warnings:
                st.markdown("**External safety warnings:**")
                for warning in warnings[:10]:
                    details = [warning.get("warningType"), warning.get("toxicityClass"), warning.get("country"), warning.get("year")]
                    references = warning.get("references") or []
                    reference = references[0] if references else None
                    label = ", ".join(str(value) for value in details if value)
                    if reference and reference.get("url"):
                        st.markdown(f"- [{label or 'Safety warning'}]({reference['url']}) · {reference.get('source', 'source link')}")
                    else:
                        st.markdown(f"- {label or 'Warning record'}")
            else:
                st.caption("No Open Targets drug warning records were returned. This is not a complete safety assessment.")

    elif not matches["error"]:
        st.info("Open Targets returned no matching medicine records.")

    with st.spinner("Searching PubMed for medicine research and safety literature…"):
        articles = search_pubmed(
            f'("{query}"[Title/Abstract]) AND (drug OR target OR mechanism OR adverse)',
            limit=5,
        )
    if articles["error"]:
        st.warning(f"PubMed is temporarily unavailable: {articles['error']}")
    elif articles["results"]:
        found_evidence = True
        st.markdown("**Source: NCBI PubMed — related medicine literature**")
        for article in articles["results"]:
            st.markdown(f"- [{article['title']}]({article['url']})")
            details = " · ".join(
                value for value in [article.get("journal"), article.get("date"), f"PMID {article['pmid']}"] if value
            )
            if details:
                st.caption(details)
        st.caption("Literature matches are references for review, not proof of efficacy or a complete safety profile.")
    elif not articles["error"]:
        st.info("PubMed returned no articles for this medicine search.")
    return found_evidence

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <h1 class="page-title">💊 Drug Profile</h1>
    <p class="page-desc">Search for a drug to view its molecular targets, approved
    indications, side effects, and biological pathways.</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: search ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Drug Search")
    drug_query = st.text_input(
        "Drug name",
        placeholder="e.g. metformin, aspirin, ibuprofen",
        help="Type part of a drug name from the DrugBank database.",
    )
    search_btn = st.button("🔍 View Profile", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("**Example drugs:**")
    example_drugs = [
        "metformin", "aspirin", "ibuprofen",
        "warfarin", "atorvastatin", "omeprazole",
        "sildenafil", "tamoxifen",
    ]
    for ex in example_drugs:
        if st.button(ex.title(), key=f"ex_drug_{ex}", use_container_width=True):
            drug_query = ex
            search_btn = True

# ── Main panel ────────────────────────────────────────────────────────────────
if not drug_query:
    st.markdown("""
    <div class="no-results">
        <p style="font-size:3rem; margin:0">💊</p>
        <p style="font-size:1.1rem; color:#C5CDD9; font-weight:500; margin:12px 0 6px 0">
            Search for a drug
        </p>
        <p>Type a drug name in the sidebar to view its full biomedical profile.</p>
        <p style="margin-top:16px; font-size:0.82rem;">
            Try: <em>Metformin</em> · <em>Aspirin</em> · <em>Warfarin</em> · <em>Sildenafil</em>
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Drug matching ─────────────────────────────────────────────────────────────
matched_drugs = search_drugs(drug_query)

if matched_drugs.empty:
    st.info(f"No local Hetionet medicine matched **'{drug_query}'**. Searching live biomedical sources.")
    found_external = show_live_drug_evidence(drug_query)
    if not found_external:
        st.warning(
            f"No useful drug information or literature was found for **'{drug_query}'** "
            "in Hetionet, Open Targets, or PubMed. Try a generic or brand-name spelling.",
            icon="🔎",
        )
    st.stop()

if len(matched_drugs) == 1:
    selected_drug_id   = matched_drugs.iloc[0]["id"]
    selected_drug_name = matched_drugs.iloc[0]["name"]
else:
    drug_options = matched_drugs["name"].tolist()
    selected_drug_name = st.selectbox(
        f"Found {len(matched_drugs)} drugs matching '{drug_query}'. Select one:",
        options=drug_options,
    )
    selected_drug_id = matched_drugs[
        matched_drugs["name"] == selected_drug_name
    ]["id"].iloc[0]

# ── Load drug profile ─────────────────────────────────────────────────────────
with st.spinner(f"Loading profile for {selected_drug_name}..."):
    profile = get_drug_profile(selected_drug_id)
    pathways = _get_drug_pathways(selected_drug_id)

if profile is None:
    st.error("Could not load drug profile. Please try another drug.")
    st.stop()

# ── Drug hero section ─────────────────────────────────────────────────────────
drugbank_id  = profile["drugbank_id"]
drug_class   = profile["drug_class"]
db_url       = f"https://www.drugbank.ca/drugs/{drugbank_id}" if drugbank_id.startswith("DB") else None

class_badge = (
    f'<span class="drug-class-badge">{drug_class}</span>'
    if drug_class and drug_class != "—"
    else ""
)
db_link = (
    f'&nbsp;&nbsp;<a href="{db_url}" target="_blank" '
    f'style="color:#00C9A7; font-size:0.85rem;">🔗 DrugBank ↗</a>'
    if db_url else ""
)

st.markdown(
    f"""
    <div class="drug-hero">
        <h1 class="drug-title">{profile['drug_name']}</h1>
        <p class="drug-id">{drugbank_id}</p>
        {class_badge}{db_link}
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Profile metrics ───────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)

metrics = [
    (m1, len(profile["targets"]),     "Molecular Targets", "Genes this drug binds"),
    (m2, len(profile["treats"]) + len(profile["palliates"]), "Indications",  "Diseases this drug treats"),
    (m3, len(profile["side_effects"]), "Side Effects",     "Adverse effects recorded"),
    (m4, len(pathways),                "Pathways",         "Biological pathways involved"),
]
for col, val, label, help_text in metrics:
    col.metric(label=label, value=val, help=help_text)

st.markdown("---")

# ── Detail sections (2 × 2 grid) ─────────────────────────────────────────────
row1_col1, row1_col2 = st.columns(2)
row2_col1, row2_col2 = st.columns(2)

# ── Molecular targets ─────────────────────────────────────────────────────────
with row1_col1:
    targets = profile["targets"]
    st.markdown(
        f'<div class="profile-card">'
        f'<p class="card-title">🧬 Molecular Targets (Genes)'
        f'<span class="count-badge">{len(targets)}</span></p>',
        unsafe_allow_html=True,
    )
    if targets:
        for t in sorted(targets)[:20]:
            st.markdown(f'<p class="list-item">• {t}</p>', unsafe_allow_html=True)
        if len(targets) > 20:
            st.caption(f"... and {len(targets) - 20} more targets")
    else:
        st.markdown('<p class="empty-label">No gene targets recorded in dataset.</p>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── Indications ───────────────────────────────────────────────────────────────
with row1_col2:
    treats    = profile["treats"]
    palliates = profile["palliates"]
    all_indications = sorted(set(treats + palliates))

    st.markdown(
        f'<div class="profile-card">'
        f'<p class="card-title">✅ Approved Indications'
        f'<span class="count-badge">{len(all_indications)}</span></p>',
        unsafe_allow_html=True,
    )
    if treats:
        st.markdown('<p style="font-size:0.75rem; color:#9EAAB8; margin:0 0 4px 0; font-weight:600;">TREATS</p>', unsafe_allow_html=True)
        for d in sorted(treats)[:10]:
            st.markdown(f'<p class="list-item">• {d}</p>', unsafe_allow_html=True)
    if palliates:
        st.markdown('<p style="font-size:0.75rem; color:#9EAAB8; margin:8px 0 4px 0; font-weight:600;">PALLIATES</p>', unsafe_allow_html=True)
        for d in sorted(palliates)[:8]:
            st.markdown(f'<p class="list-item">• {d}</p>', unsafe_allow_html=True)
    if not all_indications:
        st.markdown('<p class="empty-label">No approved indications recorded.</p>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── Side effects ──────────────────────────────────────────────────────────────
with row2_col1:
    side_effects = sorted(profile["side_effects"])

    st.markdown(
        f'<div class="profile-card">'
        f'<p class="card-title">⚠️ Known Side Effects'
        f'<span class="count-badge">{len(side_effects)}</span></p>',
        unsafe_allow_html=True,
    )
    if side_effects:
        for se in side_effects[:15]:
            st.markdown(f'<p class="list-item">• {se}</p>', unsafe_allow_html=True)
        if len(side_effects) > 15:
            st.caption(f"... and {len(side_effects) - 15} more side effects")
    else:
        st.markdown('<p class="empty-label">No side effects recorded in dataset.</p>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── Pathways ──────────────────────────────────────────────────────────────────
with row2_col2:
    st.markdown(
        f'<div class="profile-card">'
        f'<p class="card-title">🔄 Biological Pathways'
        f'<span class="count-badge">{len(pathways)}</span></p>',
        unsafe_allow_html=True,
    )
    if pathways:
        for pw in sorted(pathways)[:15]:
            st.markdown(f'<p class="list-item">• {pw}</p>', unsafe_allow_html=True)
        if len(pathways) > 15:
            st.caption(f"... and {len(pathways) - 15} more pathways")
    else:
        st.markdown('<p class="empty-label">No pathway data available for this drug.</p>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── Disclaimer ────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="warning-box">'
    '⚠️ <strong>Disclaimer:</strong> Drug profile information is sourced from the '
    'Hetionet v1.0 dataset (compiled 2015–2016) and may not reflect current '
    'clinical knowledge. This is for research and educational purposes only.'
    '</div>',
    unsafe_allow_html=True,
)

local_profile_incomplete = not (
    profile["targets"]
    and (profile["treats"] or profile["palliates"])
    and profile["side_effects"]
)
with st.expander(
    "🌐 Live Open Targets and PubMed evidence",
    expanded=local_profile_incomplete,
):
    st.caption(
        "External records supplement Hetionet and are labeled separately. "
        "Indication and warning data are not a substitute for current prescribing information."
    )
    show_live_drug_evidence(profile["drug_name"])

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"Source: Hetionet v1.0 (CC0) · DrugBank ID: {drugbank_id} · "
    "Data includes: molecular targets (CbG), indications (CtD/CpD), "
    "side effects (CcSE), pathways (CbG→GpPW)"
)
