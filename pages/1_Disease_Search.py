"""
pages/1_Disease_Search.py
─────────────────────────
Core feature: Search for a disease and discover potential repurposing candidates.

User flow:
  1. Type a disease name in the search box.
  2. Select from matched diseases if multiple found.
  3. Click "Find Candidates" to run the analysis.
  4. View ranked candidates table.
  5. Expand any candidate to read the full biological explanation.
"""

import streamlit as st
import pandas as pd

from src.repurposing import search_diseases, find_repurposing_candidates, explain_candidate
from src.biomedical_api import get_opentargets_disease, search_opentargets, search_pubmed
from src.utils import format_list, drugbank_url, pubmed_search_url, extract_raw_id

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Disease Search · Drug Repurposing",
    page_icon="🔍",
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

/* Candidate card */
.cand-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 4px;
}
.cand-name { font-size: 1.05rem; font-weight: 600; color: #F0F2F6; }
.score-badge {
    background: rgba(0,201,167,0.15);
    color: #00C9A7;
    border: 1px solid rgba(0,201,167,0.35);
    border-radius: 20px;
    padding: 2px 12px;
    font-size: 0.78rem;
    font-weight: 600;
    white-space: nowrap;
}
.info-row { font-size: 0.84rem; color: #9EAAB8; margin: 3px 0; }
.info-label { color: #C5CDD9; font-weight: 500; }
.gene-chip {
    display: inline-block;
    background: rgba(100, 149, 237, 0.12);
    border: 1px solid rgba(100, 149, 237, 0.3);
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 0.78rem;
    color: #92B4F4;
    margin: 2px 3px 2px 0;
}
.explanation-box {
    background: rgba(0, 201, 167, 0.05);
    border: 1px solid rgba(0, 201, 167, 0.2);
    border-radius: 10px;
    padding: 16px;
    margin-top: 10px;
    font-size: 0.875rem;
    line-height: 1.65;
}
.warning-box {
    background: rgba(255, 193, 7, 0.06);
    border: 1px solid rgba(255, 193, 7, 0.28);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.8rem;
    color: #C9A227;
    margin-top: 10px;
}
.source-line {
    font-size: 0.75rem;
    color: #6B7A8D;
    margin-top: 8px;
    border-top: 1px solid rgba(255,255,255,0.05);
    padding-top: 8px;
}
.no-results {
    text-align: center;
    padding: 48px 0;
    color: #6B7A8D;
    font-size: 0.95rem;
}
.result-summary {
    font-size: 0.88rem;
    color: #9EAAB8;
    margin-bottom: 16px;
    padding: 10px 16px;
    background: rgba(255,255,255,0.03);
    border-radius: 8px;
    border-left: 3px solid #00C9A7;
}
</style>
""", unsafe_allow_html=True)


def show_external_disease_evidence(disease_query: str) -> bool:
    """Show live Open Targets and PubMed evidence; return whether any was found."""
    found_evidence = False
    st.markdown("### 🌐 Live Biomedical Evidence")

    with st.spinner("Searching Open Targets for disease details and associated genes…"):
        search_result = search_opentargets(disease_query, "disease")

    if search_result["error"]:
        st.warning(f"Open Targets is temporarily unavailable: {search_result['error']}")
    elif search_result["results"]:
        hits = search_result["results"]
        if len(hits) > 1:
            hit_labels = [f"{hit.get('name', 'Unnamed disease')} — {hit.get('id')}" for hit in hits]
            selected_label = st.selectbox(
                "Choose the matching Open Targets disease",
                hit_labels,
                key="disease_search_external_choice",
            )
            hit = hits[hit_labels.index(selected_label)]
        else:
            hit = hits[0]

        with st.spinner(f"Loading Open Targets evidence for {hit.get('name', disease_query)}…"):
            detail_result = get_opentargets_disease(hit["id"])

        if detail_result["error"]:
            st.warning(f"Open Targets disease details could not be loaded: {detail_result['error']}")
        else:
            disease = detail_result["result"]
            if disease:
                found_evidence = True
                st.markdown(
                    f"**Source: Open Targets Platform** · "
                    f"[{disease['name']} — {disease['id']}]("
                    f"https://platform.opentargets.org/disease/{disease['id']}/associations)"
                )
                if disease.get("description"):
                    st.write(disease["description"])
                if disease.get("aliases"):
                    st.markdown("**Alternative names:** " + format_list(disease["aliases"], max_items=15))

                targets = disease.get("targets", [])
                if targets:
                    st.markdown(
                        "**Open Targets disease-associated genes/targets** "
                        "(association scores are not probabilities):"
                    )
                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Gene / target": row.get("symbol") or row.get("name") or row.get("id"),
                                "Ensembl ID": row.get("id"),
                                "Association score": round(row.get("score") or 0, 4),
                            }
                            for row in targets
                        ]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Open Targets returned no associated genes for this disease.")

                clinical_candidates = disease.get("clinical_candidates", [])
                if clinical_candidates:
                    found_evidence = True
                    st.markdown(
                        "**Drug-related clinical evidence from Open Targets** "
                        "(reported clinical/investigational records, not new repurposing predictions):"
                    )
                    seen_drugs = set()
                    displayed = 0
                    for candidate in clinical_candidates:
                        candidate_id = candidate.get("id")
                        candidate_name = candidate.get("name")
                        if not candidate_id or candidate_id in seen_drugs:
                            continue
                        seen_drugs.add(candidate_id)
                        stage = candidate.get("max_clinical_stage") or "Stage not reported"
                        st.markdown(
                            f"- [{candidate_name}](https://platform.opentargets.org/drug/"
                            f"{candidate_id}) — max clinical stage: `{stage}`"
                        )
                        displayed += 1
                        if displayed >= 10:
                            break
                    st.caption(
                        f"Open Targets reports {disease.get('clinical_candidate_count', 0):,} "
                        "disease-linked clinical records; up to 10 distinct medicines are shown. "
                        "These records do not establish efficacy for a new use."
                    )
                else:
                    st.info("Open Targets returned no drug-related clinical records for this disease.")
    else:
        st.info("Open Targets returned no matching disease record.")

    article_query = (
        f'("{disease_query}"[Title/Abstract]) '
        "AND (drug OR treatment OR therapeutic OR repurposing)"
    )
    with st.spinner("Searching PubMed for disease-related drug research articles…"):
        articles_result = search_pubmed(article_query, limit=6)
    if articles_result["error"]:
        st.warning(f"PubMed is temporarily unavailable: {articles_result['error']}")
    elif articles_result["results"]:
        found_evidence = True
        st.markdown("**Source: NCBI PubMed — drug/treatment literature search**")
        for article in articles_result["results"]:
            st.markdown(f"- [{article['title']}]({article['url']})")
            details = " · ".join(
                value for value in [article.get("journal"), article.get("date"), f"PMID {article['pmid']}"] if value
            )
            if details:
                st.caption(details)
        st.caption("PubMed search results are literature references; their titles alone do not prove efficacy or causality.")
    else:
        st.info("PubMed returned no articles for this disease/drug-evidence query.")

    return found_evidence

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <h1 class="page-title">🔍 Disease Search</h1>
    <p class="page-desc">Search for a disease to find potential drug repurposing candidates
    based on shared molecular targets.</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: search input ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Search Settings")
    query = st.text_input(
        "Disease name",
        placeholder="e.g. alzheimer, diabetes, asthma",
        help="Type part of a disease name. Matching diseases from Hetionet will appear.",
    )
    top_n = st.slider("Max candidates to show", min_value=5, max_value=50, value=20, step=5)
    search_btn = st.button("🔍 Find Candidates", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("**Example searches:**")
    example_diseases = [
        "alzheimer", "type 2 diabetes", "asthma",
        "breast cancer", "lung cancer", "hypertension",
        "multiple sclerosis", "parkinson",
    ]
    for ex in example_diseases:
        if st.button(ex, key=f"ex_{ex}", use_container_width=True):
            query = ex
            search_btn = True

# ── Main panel ────────────────────────────────────────────────────────────────
if not query:
    st.markdown("""
    <div class="no-results">
        <p style="font-size:3rem; margin:0">🧬</p>
        <p style="font-size:1.1rem; color:#C5CDD9; font-weight:500; margin:12px 0 6px 0">
            Start by searching for a disease
        </p>
        <p>Type a disease name in the sidebar and click <strong>Find Candidates</strong>.</p>
        <p style="margin-top:16px; font-size:0.82rem;">
            Try: <em>alzheimer</em> · <em>diabetes</em> · <em>breast cancer</em> · <em>asthma</em>
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Disease matching ──────────────────────────────────────────────────────────
matched_diseases = search_diseases(query)

if matched_diseases.empty:
    st.info(f"No local Hetionet disease matched **'{query}'**. Trying live biomedical sources.")
    with st.container():
        external_found = show_external_disease_evidence(query)
    if not external_found:
        st.warning(
            f"No disease information or supporting articles were found for **'{query}'** "
            "in Hetionet, Open Targets, or PubMed. Try an alternative disease name or spelling.",
            icon="🔎",
        )
    st.stop()

# Select disease if multiple matches
if len(matched_diseases) == 1:
    selected_row = matched_diseases.iloc[0]
    selected_disease_id   = selected_row["id"]
    selected_disease_name = selected_row["name"]
else:
    st.info(
        f"Found **{len(matched_diseases)} diseases** matching '{query}'. "
        "Please select the one you want to analyse.",
        icon="📋",
    )
    disease_options = matched_diseases["name"].tolist()
    selected_disease_name = st.selectbox(
        "Select a disease:",
        options=disease_options,
        index=0,
    )
    selected_disease_id = matched_diseases[
        matched_diseases["name"] == selected_disease_name
    ]["id"].iloc[0]

# ── Run analysis on search or button press ────────────────────────────────────
run_analysis = search_btn or (len(matched_diseases) > 0)

if not run_analysis:
    st.stop()

# ── Disease header ────────────────────────────────────────────────────────────
raw_doid = extract_raw_id(selected_disease_id)
disease_url = f"https://disease-ontology.org/term/{raw_doid.replace(':', '%3A')}"

col_title, col_link = st.columns([4, 1])
with col_title:
    st.markdown(f"## 🦠 {selected_disease_name}")
with col_link:
    st.markdown(
        f"<br><a href='{disease_url}' target='_blank' "
        f"style='color:#00C9A7; font-size:0.82rem;'>🔗 Disease Ontology ↗</a>",
        unsafe_allow_html=True,
    )

# ── Run repurposing query ─────────────────────────────────────────────────────
with st.spinner(f"Analysing drug–disease relationships for {selected_disease_name}..."):
    candidates = find_repurposing_candidates(selected_disease_id, top_n=top_n)

# ── No candidates ─────────────────────────────────────────────────────────────
if candidates is None or candidates.empty:
    external_found = show_external_disease_evidence(selected_disease_name)
    if not external_found:
        st.warning(
            f"No useful Hetionet, Open Targets, or PubMed evidence was found "
            f"for **{selected_disease_name}**. No repurposing prediction is available.",
            icon="ℹ️",
        )
    st.stop()

# ── Summary bar ───────────────────────────────────────────────────────────────
max_score = int(candidates["gene_count"].max())
st.markdown(
    f'<div class="result-summary">'
    f'Found <strong>{len(candidates)}</strong> potential repurposing candidates for '
    f'<strong>{selected_disease_name}</strong>. '
    f'Top candidate shares <strong>{max_score} connecting genes</strong>. '
    f'Results ranked by number of shared molecular targets (higher = more evidence).'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Quick summary table ───────────────────────────────────────────────────────
with st.expander("📊 View summary table (all candidates at a glance)", expanded=False):
    display_df = candidates[[
        "rank", "drug_name", "gene_count", "drug_class"
    ]].copy()
    display_df.columns = ["Rank", "Drug Name", "Connecting Genes (Score)", "Drug Class"]
    display_df["Rank"] = display_df["Rank"].astype(str)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Connecting Genes (Score)": st.column_config.ProgressColumn(
                "Score (Connecting Genes)",
                min_value=0,
                max_value=max_score,
                format="%d",
            )
        },
    )

st.markdown("---")
st.markdown(f"### Top {len(candidates)} Repurposing Candidates")

# ── Per-candidate expandable cards ────────────────────────────────────────────
for _, row in candidates.iterrows():
    rank        = int(row["rank"])
    drug_name   = row["drug_name"]
    gene_count  = int(row["gene_count"])
    genes       = row["connecting_genes"]
    indications = row["current_indications"] if isinstance(row["current_indications"], list) else []
    drug_class  = row["drug_class"]
    drug_id     = row["drug_id"]
    drugbank_id = row["drugbank_id"]

    # Format gene chips for the header preview
    gene_preview = format_list(genes, max_items=4)

    expander_label = (
        f"#{rank}  {drug_name}  ·  Score: {gene_count} "
        f"connecting {'gene' if gene_count == 1 else 'genes'}"
    )

    with st.expander(expander_label, expanded=(rank == 1)):
        col_left, col_right = st.columns([3, 2])

        with col_left:
            # Gene chips
            gene_chips_html = " ".join(
                f'<span class="gene-chip">{g}</span>'
                for g in genes[:10]
            )
            if len(genes) > 10:
                gene_chips_html += f' <span class="gene-chip">+{len(genes)-10} more</span>'

            st.markdown(
                f'<p class="info-row"><span class="info-label">Connecting Genes ({gene_count}):</span></p>'
                f'<div>{gene_chips_html}</div>',
                unsafe_allow_html=True,
            )

            if drug_class and drug_class != "—":
                st.markdown(
                    f'<p class="info-row"><span class="info-label">Drug Class:</span> {drug_class}</p>',
                    unsafe_allow_html=True,
                )

            if indications:
                ind_text = format_list(indications, max_items=5)
                st.markdown(
                    f'<p class="info-row"><span class="info-label">Currently Approved For:</span> {ind_text}</p>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<p class="info-row"><span class="info-label">Currently Approved For:</span> '
                    'No indications recorded in dataset</p>',
                    unsafe_allow_html=True,
                )

        with col_right:
            # External links
            db_url = f"https://www.drugbank.ca/drugs/{drugbank_id}" if drugbank_id.startswith("DB") else None
            pm_url = pubmed_search_url(drug_name, selected_disease_name)

            st.markdown("**External References**")
            if db_url:
                st.markdown(f"🔗 [View on DrugBank ↗]({db_url})")
            st.markdown(f"📄 [Search PubMed for evidence ↗]({pm_url})")
            st.markdown(f"🆔 `{drugbank_id}`")

        # ── Explanation section ────────────────────────────────────────────
        explanation = explain_candidate(
            drug_name=drug_name,
            disease_name=selected_disease_name,
            connecting_genes=genes,
            current_indications=indications,
            drug_class=drug_class,
            gene_count=gene_count,
            drug_id=drug_id,
        )

        st.markdown("**🔬 Biological Explanation**")
        st.markdown(
            f'<div class="explanation-box">'
            f'<p style="margin:0 0 8px 0; font-weight:600; color:#F0F2F6;">{explanation["summary"]}</p>'
            f'<p style="margin:0 0 8px 0; color:#C5CDD9;">{explanation["mechanism"]}</p>'
            f'<p style="margin:0; color:#9EAAB8;">{explanation["indications"]}</p>'
            f'<p class="source-line">{explanation["evidence"]}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="warning-box">{explanation["caveat"]}</div>',
            unsafe_allow_html=True,
        )

# ── Page footer ───────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Source: Hetionet v1.0 (CC0 public domain) · "
    "Relationships used: CbG (Compound binds Gene), GaD (Gene associates Disease) · "
    "Candidates are research hypotheses only."
)
