"""
pages/3_Graph_Explorer.py
─────────────────────────
Phase 3 feature: Interactive graph visualisation using PyVis.

Renders an interactive HTML graph for a selected disease or drug,
showing the drug → gene → disease network as a force-directed diagram.

This page requires PyVis (included in requirements.txt).
"""

import streamlit as st
import streamlit.components.v1 as components
import os
import tempfile

from src.repurposing import search_diseases, search_drugs
from src.data_loader import load_nodes, load_edges

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Graph Explorer · Drug Repurposing",
    page_icon="🕸️",
    layout="wide",
)

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
.legend-item {
    display: inline-block;
    width: 14px; height: 14px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="page-header">
    <h1 class="page-title">🕸️ Graph Explorer</h1>
    <p class="page-desc">Visualise the drug–gene–disease network for a selected disease.
    Hover over nodes to see names. Drag to rearrange.</p>
</div>
""", unsafe_allow_html=True)

# ── Check PyVis ───────────────────────────────────────────────────────────────
try:
    from pyvis.network import Network
    pyvis_available = True
except ImportError:
    pyvis_available = False

if not pyvis_available:
    st.error(
        "PyVis is not installed. Install it with:\n\n"
        "```\npip install pyvis\n```\n\n"
        "Then restart the application.",
        icon="⚠️",
    )
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Graph Settings")

    search_type = st.radio("Explore by:", ["Disease", "Drug"], index=0)

    search_q = st.text_input(
        f"{search_type} name",
        placeholder=f"e.g. {'alzheimer' if search_type == 'Disease' else 'metformin'}",
    )
    max_nodes = st.slider("Max graph nodes", min_value=20, max_value=120, value=60, step=10)
    show_side_effects = st.checkbox("Show side effects", value=False)
    build_btn = st.button("🕸️ Build Graph", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("**Legend:**")
    st.markdown(
        '<span class="legend-item" style="background:#E63946;"></span> Disease<br>'
        '<span class="legend-item" style="background:#457B9D;"></span> Drug<br>'
        '<span class="legend-item" style="background:#2A9D8F;"></span> Gene<br>'
        '<span class="legend-item" style="background:#E9C46A;"></span> Side Effect',
        unsafe_allow_html=True,
    )

# ── Default prompt ─────────────────────────────────────────────────────────────
if not search_q or not build_btn:
    st.info(
        "Enter a disease or drug name in the sidebar and click **Build Graph** "
        "to generate an interactive network diagram.",
        icon="🕸️",
    )
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
nodes_df = load_nodes()
edges_df = load_edges()
node_name_map = nodes_df.set_index("id")["name"].to_dict()


@st.cache_data(show_spinner="Building graph...")
def build_graph_data(center_id: str, center_kind: str, max_n: int, include_se: bool):
    """
    Build node/edge lists for PyVis from a central disease or drug node.
    Returns (nodes_list, edges_list) where each node is a dict and each
    edge is a (source_id, target_id, label) tuple.
    """
    graph_nodes = {}  # id -> {label, color, title}
    graph_edges = []  # list of (src, tgt, label)

    def add_node(node_id, kind):
        if node_id in graph_nodes:
            return True
        if len(graph_nodes) >= max_n:
            return False
        name = node_name_map.get(node_id, node_id)
        colors = {
            "Disease":            "#E63946",
            "Compound":           "#457B9D",
            "Gene":               "#2A9D8F",
            "Side Effect":        "#E9C46A",
            "Pharmacologic Class": "#A8DADC",
            "Pathway":            "#6C757D",
        }
        graph_nodes[node_id] = {
            "label": name[:30] + ("…" if len(name) > 30 else ""),
            "title": f"{kind}: {name}",
            "color": colors.get(kind, "#888888"),
            "size":  25 if kind in ("Disease", "Compound") else 15,
        }
        return True

    if center_kind == "Disease":
        # Disease → genes (GaD) → drugs (CbG)
        add_node(center_id, "Disease")

        gene_edges = edges_df[
            (edges_df["metaedge"] == "GaD") & (edges_df["target"] == center_id)
        ].head(max_n // 2)

        gene_ids = gene_edges["source"].tolist()
        for gid in gene_ids:
            add_node(gid, "Gene")
            graph_edges.append((gid, center_id, "associates"))

        # Drugs binding those genes
        drug_gene_edges = edges_df[
            (edges_df["metaedge"] == "CbG") & (edges_df["target"].isin(gene_ids))
        ]
        # Pick top drugs (most connecting genes)
        top_drugs = (
            drug_gene_edges.groupby("source")["target"]
            .count()
            .sort_values(ascending=False)
            .head(max_n // 3)
            .index.tolist()
        )
        for did in top_drugs:
            add_node(did, "Compound")
            for _, row in drug_gene_edges[drug_gene_edges["source"] == did].iterrows():
                if row["target"] in graph_nodes:
                    graph_edges.append((did, row["target"], "binds"))

        # Existing treatments (green edges)
        treat_edges = edges_df[
            (edges_df["metaedge"].isin(["CtD", "CpD"])) & (edges_df["target"] == center_id)
        ].head(15)
        for _, row in treat_edges.iterrows():
            add_node(row["source"], "Compound")
            graph_edges.append((row["source"], center_id, "treats"))

    else:
        # Drug → genes (CbG) → diseases (GaD)
        add_node(center_id, "Compound")

        gene_edges = edges_df[
            (edges_df["metaedge"] == "CbG") & (edges_df["source"] == center_id)
        ].head(max_n // 3)

        gene_ids = gene_edges["target"].tolist()
        for gid in gene_ids:
            add_node(gid, "Gene")
            graph_edges.append((center_id, gid, "binds"))

        # Diseases via those genes
        dis_edges = edges_df[
            (edges_df["metaedge"] == "GaD") & (edges_df["source"].isin(gene_ids))
        ].head(max_n // 2)
        for _, row in dis_edges.iterrows():
            add_node(row["target"], "Disease")
            if row["source"] in graph_nodes:
                graph_edges.append((row["source"], row["target"], "associates"))

        # Side effects
        if include_se:
            se_edges = edges_df[
                (edges_df["metaedge"] == "CcSE") & (edges_df["source"] == center_id)
            ].head(15)
            for _, row in se_edges.iterrows():
                add_node(row["target"], "Side Effect")
                graph_edges.append((center_id, row["target"], "causes"))

    return graph_nodes, graph_edges


# ── Find center node ──────────────────────────────────────────────────────────
if search_type == "Disease":
    matched = search_diseases(search_q)
else:
    matched = search_drugs(search_q)

if matched.empty:
    st.warning(f"No {search_type.lower()} found matching '{search_q}'.", icon="🔎")
    st.stop()

if len(matched) == 1:
    center_id   = matched.iloc[0]["id"]
    center_name = matched.iloc[0]["name"]
else:
    selected_name = st.selectbox(
        f"Multiple matches found. Select one:",
        options=matched["name"].tolist(),
    )
    center_id   = matched[matched["name"] == selected_name]["id"].iloc[0]
    center_name = selected_name

center_kind = "Disease" if search_type == "Disease" else "Compound"

# ── Build graph data ──────────────────────────────────────────────────────────
with st.spinner("Building network graph..."):
    graph_nodes, graph_edges = build_graph_data(
        center_id, center_kind, max_nodes, show_side_effects
    )

st.markdown(
    f"**Network for: {center_name}** · "
    f"{len(graph_nodes)} nodes · {len(graph_edges)} edges"
)

# ── PyVis network ─────────────────────────────────────────────────────────────
net = Network(
    height="600px",
    width="100%",
    bgcolor="#0E1117",
    font_color="#F0F2F6",
    directed=True,
)
net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=150)

for node_id, attrs in graph_nodes.items():
    net.add_node(
        node_id,
        label=attrs["label"],
        title=attrs["title"],
        color=attrs["color"],
        size=attrs["size"],
        font={"size": 10, "color": "#F0F2F6"},
    )

edge_colors = {
    "binds":      "#2A9D8F",
    "associates": "#E63946",
    "treats":     "#00C9A7",
    "causes":     "#E9C46A",
}
for src, tgt, label in graph_edges:
    if src in graph_nodes and tgt in graph_nodes:
        net.add_edge(
            src, tgt,
            title=label,
            color=edge_colors.get(label, "#666666"),
            width=1.5,
        )

# Save and embed
with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
    tmp_path = f.name

net.save_graph(tmp_path)
with open(tmp_path, "r", encoding="utf-8") as f:
    html_content = f.read()
os.unlink(tmp_path)

components.html(html_content, height=620, scrolling=False)

# ── Legend ────────────────────────────────────────────────────────────────────
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)
col1.markdown("🔴 Disease node")
col2.markdown("🔵 Drug (Compound) node")
col3.markdown("🟢 Gene node")
col4.markdown("🟡 Side Effect node")

st.caption(
    "Graph shows a subgraph around the selected node. "
    "Drag nodes to rearrange. Scroll to zoom. Hover for full names. "
    "Source: Hetionet v1.0"
)
