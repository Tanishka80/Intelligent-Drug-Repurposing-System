"""
app.py — Home page
──────────────────
Entry point for the Streamlit application.
Run with:  streamlit run app.py
"""

import streamlit as st

# ── Page config (must be the first Streamlit call) ──────────────────────────
st.set_page_config(
    page_title="Drug Repurposing Research Assistant",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Import Google Font */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Global font */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Hero section */
.hero-container {
    background: linear-gradient(135deg, #0D1B2A 0%, #1B2A3B 50%, #0D2137 100%);
    border: 1px solid rgba(0, 201, 167, 0.25);
    border-radius: 16px;
    padding: 48px 40px;
    margin-bottom: 32px;
    text-align: center;
}
.hero-title {
    font-size: 2.6rem;
    font-weight: 700;
    color: #FFFFFF;
    margin: 0 0 12px 0;
    letter-spacing: -0.5px;
}
.hero-subtitle {
    font-size: 1.1rem;
    color: #9EAAB8;
    margin: 0 0 24px 0;
    line-height: 1.7;
    max-width: 680px;
    margin-left: auto;
    margin-right: auto;
}
.badge {
    display: inline-block;
    background: rgba(0, 201, 167, 0.15);
    color: #00C9A7;
    border: 1px solid rgba(0, 201, 167, 0.35);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 18px;
}

/* Stat cards */
.stat-card {
    background: #1A1F2E;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 24px 20px;
    text-align: center;
}
.stat-number {
    font-size: 2rem;
    font-weight: 700;
    color: #00C9A7;
    margin: 0;
}
.stat-label {
    font-size: 0.82rem;
    color: #9EAAB8;
    margin: 4px 0 0 0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Feature cards */
.feature-card {
    background: #1A1F2E;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 24px 20px;
    height: 100%;
}
.feature-icon {
    font-size: 1.8rem;
    margin-bottom: 10px;
}
.feature-title {
    font-size: 1rem;
    font-weight: 600;
    color: #F0F2F6;
    margin: 0 0 8px 0;
}
.feature-desc {
    font-size: 0.85rem;
    color: #9EAAB8;
    line-height: 1.6;
}

/* Disclaimer banner */
.disclaimer {
    background: rgba(255, 193, 7, 0.07);
    border: 1px solid rgba(255, 193, 7, 0.3);
    border-radius: 10px;
    padding: 16px 20px;
    font-size: 0.85rem;
    color: #C9A227;
    margin-top: 32px;
}

/* Section headings */
.section-heading {
    font-size: 1.15rem;
    font-weight: 600;
    color: #F0F2F6;
    margin: 32px 0 16px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
}
</style>
""", unsafe_allow_html=True)

# ── Load data (cached) ───────────────────────────────────────────────────────
# Community Cloud starts with a clean filesystem, so prepare the ignored dataset
# automatically on first launch when it is not already present.
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
NODES_FILE = DATA_DIR / "hetionet-v1.0-nodes.tsv"
EDGES_FILE = DATA_DIR / "edges_filtered.tsv"

try:
    if not NODES_FILE.exists() or not EDGES_FILE.exists():
        with st.spinner("Preparing the Hetionet biomedical dataset for first launch. This may take several minutes..."):
            setup_result = subprocess.run(
                [sys.executable, str(Path(__file__).parent / "setup_data.py")],
                cwd=str(Path(__file__).parent),
                capture_output=True,
                text=True,
                check=False,
            )
        if setup_result.returncode != 0:
            raise RuntimeError(
                "Dataset setup failed. " +
                (setup_result.stderr[-3000:] or setup_result.stdout[-3000:])
            )

    from src.data_loader import get_dataset_stats
    stats = get_dataset_stats()
    data_loaded = True
except Exception as e:
    data_loaded = False
    data_error = str(e)

# ── Hero Section ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-container">
    <div class="badge">MedNex</div>
    <h1 class="hero-title">💊 Intelligent Drug Repurposing<br>Research Assistant</h1>
    <p class="hero-subtitle">
        Discover potential new uses for existing drugs by analysing molecular targets
        and gene–disease relationships from the Hetionet biomedical knowledge graph.
    </p>
</div>
""", unsafe_allow_html=True)

# ── Data load error ───────────────────────────────────────────────────────────
if not data_loaded:
    st.error(
        "**Data files not found.**\n\n"
        f"Automatic dataset preparation could not complete: {data_error}",
        icon="⚠️",
    )
    st.stop()

# ── Dataset Statistics ────────────────────────────────────────────────────────
st.markdown('<p class="section-heading">Dataset Overview — Hetionet v1.0</p>', unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)

stat_items = [
    (c1, stats["n_drugs"],            "Drugs (Compounds)"),
    (c2, stats["n_diseases"],         "Diseases"),
    (c3, stats["n_genes"],            "Genes / Targets"),
    (c4, stats["n_known_treatments"], "Treatment Links"),
    (c5, stats["n_side_effects"],     "Side Effects"),
]

for col, value, label in stat_items:
    with col:
        st.markdown(f"""
        <div class="stat-card">
            <p class="stat-number">{value:,}</p>
            <p class="stat-label">{label}</p>
        </div>
        """, unsafe_allow_html=True)

# ── Features Overview ─────────────────────────────────────────────────────────
st.markdown('<p class="section-heading">What You Can Do</p>', unsafe_allow_html=True)

f1, f2, f3 = st.columns(3)

with f1:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">🔍</div>
        <p class="feature-title">Disease Search & Repurposing</p>
        <p class="feature-desc">
            Search for any disease in the dataset and discover drugs that
            may be repurposed for it based on shared molecular targets.
            Candidates are ranked by the number of connecting genes.
        </p>
    </div>
    """, unsafe_allow_html=True)

with f2:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">💡</div>
        <p class="feature-title">Biological Pathway Explanation</p>
        <p class="feature-desc">
            For each candidate, see the exact genes connecting the drug
            to the disease, a plain-English explanation of the relationship,
            and the data sources behind the association.
        </p>
    </div>
    """, unsafe_allow_html=True)

with f3:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">📋</div>
        <p class="feature-title">Drug Profile Viewer</p>
        <p class="feature-desc">
            View a complete profile for any drug: molecular targets,
            current approved indications, side effects, biological
            pathways, and drug class classification.
        </p>
    </div>
    """, unsafe_allow_html=True)

# ── How It Works ──────────────────────────────────────────────────────────────
st.markdown('<p class="section-heading">How Repurposing Works</p>', unsafe_allow_html=True)

with st.expander("Click to understand the scientific method used", expanded=False):
    st.markdown("""
    #### The Two-Hop Path Approach

    This system identifies repurposing candidates by finding drugs that share molecular
    targets with a disease, using a two-step graph traversal:

    ```
    Drug ──[binds]──► Gene ──[associated with]──► Disease
    ```

    **Step 1:** Find all genes genetically associated with the target disease.

    **Step 2:** Find all drugs that bind (or regulate) those genes.

    **Step 3:** Remove drugs already approved for that disease — they are not "repurposed".

    **Step 4:** Rank remaining drugs by the number of connecting genes.
    A higher count means more molecular evidence supporting the hypothesis.

    #### Ranking Score

    > **Score = number of distinct shared genes**

    This is a simple, transparent, and explainable metric. A drug with 8 connecting
    genes has more convergent biological evidence than a drug with 1 connecting gene.

    #### Data Source

    All relationships come from **Hetionet v1.0** (CC0 public domain), which
    integrates 29 curated biomedical databases including DrugBank, OMIM,
    DisGeNET, Reactome, Gene Ontology, and SIDER.
    """)

# ── Quick Start ───────────────────────────────────────────────────────────────
st.markdown('<p class="section-heading">Get Started</p>', unsafe_allow_html=True)

col_a, col_b = st.columns(2)
with col_a:
    st.info(
        "**👈 Use the sidebar** to navigate between pages.\n\n"
        "Start with **Disease Search** to find repurposing candidates for a disease of interest."
    )
with col_b:
    st.info(
        "**Example searches to try:**\n\n"
        "🔬 `alzheimer` · `diabetes` · `asthma` · `breast cancer` · `lung cancer`"
    )

st.info(
    "**🧪 Research Assistant:** Use the sidebar page to search diseases and medicines, "
    "review live Open Targets and PubMed evidence, upload a medicine label for OCR, "
    "or ask a retrieval-grounded biomedical question."
)

# ── Disclaimer ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="disclaimer">
    <strong>⚠️ Research Tool Disclaimer</strong><br>
    All drug–disease associations displayed by this application are
    <strong>computational research hypotheses</strong> based on molecular target overlap
    in the Hetionet dataset. They have <strong>not been clinically validated</strong>
    and should <strong>not</strong> be used to make any medical decisions.
    Always consult a qualified healthcare professional.
</div>
""", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Data: Hetionet v1.0 (CC0) · "
    "Built with Streamlit, Pandas · "
    "BTech Final-Year Project"
)
