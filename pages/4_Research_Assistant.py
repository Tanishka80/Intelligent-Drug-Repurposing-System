"""Local-first biomedical search, evidence review, image OCR and Q&A."""

from __future__ import annotations

import io
import os
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from PIL import Image, ImageOps

from src.biomedical_api import (
    get_opentargets_disease,
    get_opentargets_drug,
    pubmed_pair_query,
    search_opentargets,
    search_pubmed,
)
from src.data_loader import load_edges, load_nodes
from src.repurposing import (
    explain_candidate,
    find_repurposing_candidates,
    get_drug_profile,
    search_diseases,
    search_drugs,
)
from src.utils import format_list

st.set_page_config(
    page_title="Research Assistant · Drug Repurposing",
    page_icon="🧪",
    layout="wide",
)

st.markdown("""
<style>
:root { --teal: #00C9A7; }
.block-container { padding-top: 1.5rem; }
.research-note { padding: .8rem 1rem; border-left: 3px solid #00C9A7;
  background: rgba(0,201,167,.06); border-radius: 6px; }
.source-local { color: #00C9A7; font-weight: 600; }
.source-live { color: #8AB4F8; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

st.title("🧪 Biomedical Research Assistant")
st.markdown(
    "Search Hetionet first, then consult public Open Targets and PubMed records. "
    "Results identify evidence and research leads—not treatment advice."
)
st.info(
    "Answers are assembled from retrieved records and transparent relationship checks; "
    "no generative AI model is configured, so unsupported facts or predictions are not invented. "
    "External data requires an internet connection.",
    icon="ℹ️",
)


def _normalize(value: str) -> str:
    text = str(value).casefold().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _show_api_error(error: Optional[str], source: str) -> None:
    if error:
        st.caption(f"{source} could not be reached. Local results remain available. ({error})")


def _render_pubmed(query: str, label: str = "Related PubMed records") -> None:
    result = search_pubmed(query, limit=5)
    if result["error"]:
        _show_api_error(result["error"], "PubMed")
    elif result["results"]:
        with st.expander(f"📚 {label} ({len(result['results'])})", expanded=False):
            for citation in result["results"]:
                st.markdown(f"- [{citation['title']}]({citation['url']})")
                st.caption(" · ".join(part for part in [citation["journal"], citation["date"], f"PMID {citation['pmid']}"] if part))
    else:
        st.caption("No PubMed records were returned for this search.")


def _disease_local_evidence(disease_id: str) -> Tuple[List[str], List[str]]:
    nodes, edges = load_nodes(), load_edges()
    name_map = nodes.set_index("id")["name"].to_dict()
    rows = edges[(edges["metaedge"] == "GaD") & (edges["target"] == disease_id)]
    gene_ids = sorted(set(rows["source"]))
    gene_names = sorted({name_map.get(gene_id, gene_id) for gene_id in gene_ids})
    return gene_ids, gene_names


def _opentargets_for_name(query: str, entity: str) -> Tuple[Optional[Dict], Optional[str]]:
    result = search_opentargets(query, entity)
    if result["error"]:
        return None, result["error"]
    if not result["results"]:
        return None, None
    # Prefer the exact normalized name when the API returns one; otherwise keep
    # the top ranked search hit visible as a suggestion instead of auto-asserting it.
    exact = [hit for hit in result["results"] if _normalize(hit.get("name", "")) == _normalize(query)]
    if exact:
        return exact[0], None
    ranked = sorted(
        result["results"],
        key=lambda hit: SequenceMatcher(None, _normalize(query), _normalize(hit.get("name", ""))).ratio(),
        reverse=True,
    )
    if ranked and SequenceMatcher(None, _normalize(query), _normalize(ranked[0].get("name", ""))).ratio() >= 0.72:
        return ranked[0], None
    return None, None


def _display_local_drug(drug_id: str) -> None:
    profile = get_drug_profile(drug_id)
    if not profile:
        st.warning("The selected local drug profile could not be loaded.")
        return
    st.markdown("**Source: Hetionet v1.0 local dataset**")
    a, b = st.columns(2)
    with a:
        st.markdown("**Genes / molecular targets**")
        st.write(format_list(profile["targets"], max_items=20))
        st.markdown("**Recorded disease indications**")
        st.write(format_list(profile["treats"] + profile["palliates"], max_items=15))
    with b:
        st.markdown("**Drug class**")
        st.write(profile["drug_class"] or "Not recorded")
        st.markdown("**Side effects in Hetionet**")
        st.write(format_list(profile["side_effects"], max_items=15))


def _display_external_drug(chembl_id: str) -> None:
    response = get_opentargets_drug(chembl_id)
    if response["error"]:
        _show_api_error(response["error"], "Open Targets")
        return
    drug = response["result"]
    if not drug:
        st.info("Open Targets returned no detailed profile for this medicine.")
        return
    st.markdown(f"**Source: live Open Targets data** · [{drug['id']}](https://platform.opentargets.org/drug/{drug['id']})")
    st.write(drug.get("description") or "No description is available from Open Targets.")
    if drug.get("trade_names"):
        st.markdown("**Trade-name suggestions:** " + format_list(drug["trade_names"], max_items=15))
    if drug.get("mechanisms"):
        st.markdown("**Reported mechanisms:** " + format_list(drug["mechanisms"], max_items=10))
    targets = drug.get("targets") or []
    if targets:
        target_names = [f"{target.get('approvedSymbol') or target.get('approvedName') or target['id']} ({target['id']})" for target in targets]
        st.markdown("**Mechanism-linked targets:** " + format_list(target_names, max_items=20))
    else:
        st.info("No mechanism-linked targets were returned for this medicine.")
    if drug.get("indications"):
        st.markdown("**Indications listed by Open Targets:** " + format_list(drug["indications"], max_items=20))
    st.caption("Open Targets drug record; indication records are not a substitute for current regulatory labeling.")


def _local_mentions(text: str, kind: str) -> List[Dict[str, str]]:
    nodes = load_nodes()
    subset = nodes[nodes["kind"] == kind][["id", "name"]]
    normalized_text = _normalize(text)
    found = []
    for row in subset.itertuples(index=False):
        name = str(row.name)
        normalized_name = _normalize(name)
        if len(normalized_name) >= 4 and normalized_name in normalized_text:
            found.append({"id": row.id, "name": name})
    found.sort(key=lambda hit: len(_normalize(hit["name"])), reverse=True)
    # Avoid returning shorter nested names if a more specific name contains it.
    unique = []
    seen_ids = set()
    for hit in found:
        if hit["id"] not in seen_ids:
            unique.append(hit)
            seen_ids.add(hit["id"])
    return unique[:5]


def _unresolved_search_term(text: str, entities: List[Dict[str, str]]) -> str:
    """Extract meaningful words not already explained by local entity matches."""
    stop_words = {
        "can", "could", "would", "should", "be", "is", "are", "was", "were",
        "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with",
        "what", "which", "who", "how", "why", "this", "that", "these", "those",
        "it", "its", "my", "me", "show", "tell", "about", "find", "search",
        "associated", "linked", "related", "investigated", "investigate", "repurposed",
        "repurposing", "potentially", "potential", "another", "new", "use", "used",
        "treat", "treatment", "target", "targets", "gene", "genes", "molecular",
        "medicine", "medicines", "drug", "drugs", "disease", "diseases", "condition",
        "conditions", "side", "effects", "known", "information", "evidence", "for",
    }
    entity_words = set()
    for entity in entities:
        entity_words.update(re.findall(r"[a-z0-9]+", entity.get("name", "").casefold()))
        entity_words.add(_normalize(entity.get("name", "")))
    words = re.findall(r"[a-z0-9]+", text.casefold())
    remaining = [
        word for word in words
        if len(word) >= 3 and word not in stop_words and word not in entity_words
    ]
    return " ".join(remaining[:4])


def _match_pair(drug_id: Optional[str], disease_id: Optional[str]) -> Dict[str, List[str]]:
    if not drug_id or not disease_id:
        return {"genes": [], "source": []}
    edges, nodes = load_edges(), load_nodes()
    drug_targets = set(edges[(edges["metaedge"] == "CbG") & (edges["source"] == drug_id)]["target"])
    disease_targets = set(edges[(edges["metaedge"] == "GaD") & (edges["target"] == disease_id)]["source"])
    names = nodes.set_index("id")["name"].to_dict()
    return {"genes": sorted(names.get(gene, gene) for gene in drug_targets & disease_targets), "source": ["Hetionet CbG", "Hetionet GaD"]}


tab_disease, tab_drug, tab_image, tab_qa = st.tabs([
    "🦠 Disease Search", "💊 Drug Search", "📷 Medicine Image", "💬 Ask a Question"
])

with tab_disease:
    st.subheader("Disease search")
    st.caption("Search local Hetionet names first. Live Open Targets and PubMed results are labelled separately.")
    with st.form("disease_search_form"):
        disease_query = st.text_input("Disease, condition, alias, or partial name", key="research_disease_query", placeholder="e.g. Alzheimer’s, asthma, type 2 diabetes")
        disease_submit = st.form_submit_button("Search disease", type="primary")
    if disease_submit and disease_query.strip():
        st.session_state["research_active_disease_query"] = disease_query.strip()
    disease_query = st.session_state.get("research_active_disease_query", "")
    if disease_query:
        local_diseases = search_diseases(disease_query)
        selected_local_disease = None
        if not local_diseases.empty:
            st.markdown('<span class="source-local">LOCAL · Hetionet v1.0</span>', unsafe_allow_html=True)
            local_names = local_diseases["name"].tolist()
            selected_name = st.selectbox("Matching Hetionet diseases", local_names, key="research_disease_choice")
            selected_local_disease = local_diseases[local_diseases["name"] == selected_name].iloc[0]
            local_id = selected_local_disease["id"]
            local_gene_ids, local_genes = _disease_local_evidence(local_id)
            st.markdown(f"**{selected_name}** · {len(local_genes)} disease-associated genes recorded")
            st.write(format_list(local_genes, max_items=25) if local_genes else "No disease–gene links are recorded locally.")
            st.markdown(f"[Hetionet disease node `{local_id}`](https://disease-ontology.org/)")
        else:
            st.info("No local Hetionet disease matched. Searching the live biomedical source next.")

        with st.spinner("Searching Open Targets for disease names, synonyms and targets…"):
            ot_query = selected_local_disease["name"] if selected_local_disease is not None else disease_query
            ot_hits = search_opentargets(ot_query, "disease")
        _show_api_error(ot_hits["error"], "Open Targets")
        if ot_hits["results"]:
            st.markdown('<span class="source-live">LIVE · Open Targets Platform</span>', unsafe_allow_html=True)
            api_names = [f"{hit.get('name', 'Unnamed')} — {hit.get('id')}" for hit in ot_hits["results"]]
            api_choice = st.selectbox("Open Targets matches / alternative names", api_names, key="research_disease_ot_choice")
            hit = ot_hits["results"][api_names.index(api_choice)]
            disease_response = get_opentargets_disease(hit["id"])
            _show_api_error(disease_response["error"], "Open Targets disease details")
            ext = disease_response["result"]
            if ext:
                st.markdown(f"**{ext['name']}** · [{ext['id']}](https://platform.opentargets.org/disease/{ext['id']}/associations)")
                st.write(ext.get("description") or "No disease description is available from Open Targets.")
                if ext.get("aliases"):
                    st.markdown("**Alternative names:** " + format_list(ext["aliases"], max_items=15))
                targets = ext.get("targets", [])
                if targets:
                    st.markdown("**Associated targets** (Open Targets association scores shown, not probabilities):")
                    st.dataframe(pd.DataFrame([
                        {"Gene / target": item.get("symbol") or item.get("name") or item["id"], "Ensembl ID": item.get("id"), "Association score": round(item.get("score", 0), 4)}
                        for item in targets
                    ]), use_container_width=True, hide_index=True)
                else:
                    st.info("Open Targets returned no target associations for this disease.")
                st.caption(f"Open Targets reports {ext.get('target_count', 0):,} associated targets in total; showing up to 20.")
        elif not ot_hits["error"]:
            st.info("No matching disease names were returned by Open Targets.")

        if selected_local_disease is None and not ot_hits["results"]:
            st.warning("No matching disease information was found in Hetionet or Open Targets.")
        _render_pubmed(f'("{disease_query}"[Title/Abstract])', "PubMed disease literature")

with tab_drug:
    st.subheader("Medicine search")
    st.caption("Generic, partial, fuzzy and live API matches are presented as suggestions. Confirm the intended medicine before using its details.")
    with st.form("drug_search_form"):
        drug_query = st.text_input("Medicine, generic name, brand name, or partial name", key="research_drug_query", placeholder="e.g. metformin, aspirin, Tylenol")
        drug_submit = st.form_submit_button("Search medicine", type="primary")
    if drug_submit and drug_query.strip():
        st.session_state["research_active_drug_query"] = drug_query.strip()
    drug_query = st.session_state.get("research_active_drug_query", "")
    if drug_query:
        local_drugs = search_drugs(drug_query)
        selected_local_drug = None
        if not local_drugs.empty:
            st.markdown('<span class="source-local">LOCAL · Hetionet v1.0</span>', unsafe_allow_html=True)
            local_names = local_drugs["name"].tolist()
            selected_name = st.selectbox("Matching Hetionet medicines", local_names, key="research_drug_choice")
            selected_local_drug = local_drugs[local_drugs["name"] == selected_name].iloc[0]
            _display_local_drug(selected_local_drug["id"])
        else:
            st.info("No local Hetionet medicine matched. Searching live Open Targets records next.")

        with st.spinner("Searching Open Targets for generic and trade-name matches…"):
            ot_query = selected_local_drug["name"] if selected_local_drug is not None else drug_query
            ot_hits = search_opentargets(ot_query, "drug")
        _show_api_error(ot_hits["error"], "Open Targets")
        if ot_hits["results"]:
            st.markdown('<span class="source-live">LIVE · Open Targets Platform</span>', unsafe_allow_html=True)
            api_names = [f"{hit.get('name', 'Unnamed')} — {hit.get('id')}" for hit in ot_hits["results"]]
            api_choice = st.selectbox("Open Targets medicine matches", api_names, key="research_drug_ot_choice")
            hit = ot_hits["results"][api_names.index(api_choice)]
            _display_external_drug(hit["id"])
        elif not ot_hits["error"]:
            st.info("No medicine matches were returned by Open Targets.")

        if selected_local_drug is None and not ot_hits["results"]:
            st.warning("No matching medicine information was found in Hetionet or Open Targets. Try a generic or brand name spelling.")
        _render_pubmed(f'("{drug_query}"[Title/Abstract])', "PubMed medicine literature")

with tab_image:
    st.subheader("Read a medicine label")
    st.markdown(
        "Upload a clear photo of the **printed label**. OCR reads visible text only; "
        "it does not identify a medicine from shape, color, or packaging appearance. "
        "You must review and confirm any suggested name."
    )
    with st.expander("OCR setup instructions for Windows"):
        st.markdown(
            "1. Install the Python packages with `python -m pip install -r requirements.txt`.\n"
            "2. Install the Tesseract OCR engine using the [Windows installer instructions](https://github.com/UB-Mannheim/tesseract/wiki).\n"
            "3. In PowerShell, set the executable path before starting Streamlit:\n"
        )
        st.code(
            '$env:TESSERACT_CMD = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"\n'
            "python -m streamlit run app.py",
            language="powershell",
        )
        st.caption("Adjust the path if Tesseract was installed in a different folder. OCR only extracts printed text; confirm the medicine name manually.")
    uploaded = st.file_uploader("Upload medicine strip, bottle, box, or label", type=["png", "jpg", "jpeg", "webp"], key="medicine_image_upload")
    if uploaded is not None:
        try:
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(uploaded.getvalue()))).convert("RGB")
            st.image(image, caption="Uploaded label image", use_container_width=True)
            try:
                import pytesseract
                command = os.getenv("TESSERACT_CMD")
                if command:
                    pytesseract.pytesseract.tesseract_cmd = command
                with st.spinner("Reading visible label text with OCR…"):
                    ocr_image = ImageOps.autocontrast(image.convert("L"))
                    if ocr_image.width < 1400:
                        ratio = 1400 / ocr_image.width
                        ocr_image = ocr_image.resize((1400, int(ocr_image.height * ratio)))
                    recognized_text = pytesseract.image_to_string(ocr_image, lang="eng")
                recognized_text = recognized_text.strip()
                if recognized_text:
                    st.text_area("OCR text — review/correct before searching", value=recognized_text, height=140, key="medicine_ocr_text")
                    default_name = next((line.strip() for line in recognized_text.splitlines() if any(char.isalpha() for char in line)), "")
                    medicine_name = st.text_input("Medicine name to look up", value=default_name[:100], key="ocr_medicine_name")
                    matches = search_drugs(medicine_name) if medicine_name.strip() else pd.DataFrame()
                    if matches.empty and medicine_name.strip():
                        st.info("No local match for the OCR text. We will check Open Targets after you choose a likely name.")
                        live_matches = search_opentargets(medicine_name, "drug")
                        _show_api_error(live_matches["error"], "Open Targets")
                        if live_matches["results"]:
                            labels = [f"{item.get('name', 'Unnamed')} — {item.get('id')}" for item in live_matches["results"]]
                            selected = st.selectbox("Possible medicine matches (suggestions only)", labels, key="ocr_ot_choice")
                            candidate = live_matches["results"][labels.index(selected)]
                            confirmed = st.checkbox(f"I confirm the label text is intended to identify {candidate.get('name')} ({candidate.get('id')}).", key="ocr_ot_confirm")
                            if confirmed:
                                _display_external_drug(candidate["id"])
                    elif not matches.empty:
                        local_names = matches["name"].tolist()
                        selected = st.selectbox("Possible Hetionet matches (suggestions only)", local_names, key="ocr_local_choice")
                        candidate = matches[matches["name"] == selected].iloc[0]
                        confirmed = st.checkbox(f"I confirm the printed name is {selected}.", key="ocr_local_confirm")
                        if confirmed:
                            _display_local_drug(candidate["id"])
                            api_hit, api_error = _opentargets_for_name(selected, "drug")
                            _show_api_error(api_error, "Open Targets")
                            if api_hit:
                                _display_external_drug(api_hit["id"])
                else:
                    st.warning("OCR could not read visible text. Try a sharper, well-lit image or enter the printed medicine name in the Drug Search tab.")
            except ImportError:
                st.error("OCR support is not installed. Run `pip install -r requirements.txt` and restart the app.")
            except Exception as exc:
                if type(exc).__name__ == "TesseractNotFoundError":
                    st.error("The Tesseract OCR engine was not found. Follow the Windows OCR setup instructions above, then restart Streamlit. No medicine was identified from the image.")
                else:
                    st.error("OCR could not read this image. Try a sharper, well-lit photo. No medicine was identified from the image.")
                st.caption(str(exc))
        except Exception as exc:
            st.error("The uploaded file could not be opened as an image.")
            st.caption(str(exc))
    else:
        st.caption("Supported image formats: PNG, JPG/JPEG, WEBP. OCR requires the Tesseract executable in addition to the Python package.")

with tab_qa:
    st.subheader("Ask a biomedical research question")
    st.caption("The assistant searches local records, then relevant live sources. Include the medicine/disease name; pronouns such as ‘this drug’ need explicit context.")
    question = st.text_area(
        "Your question",
        placeholder="What genes and molecular targets are linked to Alzheimer's disease?\nCan aspirin be investigated for Alzheimer's disease?",
        height=100,
        key="research_question",
    )
    context = st.text_input("Optional context or additional medicine/disease name", key="research_context", placeholder="e.g. aspirin; Alzheimer’s disease")
    context_type = st.selectbox(
        "Context type if the name is not in Hetionet",
        ["Auto-detect", "Disease", "Medicine"],
        key="research_context_type",
    )
    answer_clicked = st.button("🔎 Retrieve evidence and answer", type="primary", key="answer_research_question")

    if answer_clicked:
        if not question.strip():
            st.warning("Enter a question to search the biomedical records.")
        else:
            combined = f"{question} {context}".strip()
            disease_mentions = _local_mentions(combined, "Disease")
            drug_mentions = _local_mentions(combined, "Compound")
            explicit_context = context.strip()
            if explicit_context and not disease_mentions and not drug_mentions:
                # Local fuzzy matching is attempted before any external query.
                disease_candidates = search_diseases(explicit_context)
                drug_candidates = search_drugs(explicit_context)
                if not disease_candidates.empty:
                    disease_mentions = [{"id": disease_candidates.iloc[0]["id"], "name": disease_candidates.iloc[0]["name"]}]
                if not drug_candidates.empty:
                    drug_mentions = [{"id": drug_candidates.iloc[0]["id"], "name": drug_candidates.iloc[0]["name"]}]
            disease = disease_mentions[0] if disease_mentions else None
            drug = drug_mentions[0] if drug_mentions else None
            unresolved_term = _unresolved_search_term(combined, disease_mentions + drug_mentions)
            repurposing_question = any(word in question.casefold() for word in ("repurpos", "investigat", "another disease", "potential use", "new use"))
            answer_parts = []

            missing_entity = "drug" if disease and not drug else "disease" if drug and not disease else None
            if missing_entity and unresolved_term:
                with st.spinner(f"Searching Open Targets for the unrecognized {missing_entity} name…"):
                    unresolved_matches = search_opentargets(unresolved_term, missing_entity)
                _show_api_error(unresolved_matches["error"], "Open Targets")
                if unresolved_matches["results"]:
                    st.markdown(f"**Live Open Targets {missing_entity} matches** — select the intended record:")
                    match_labels = [
                        f"{item.get('name', 'Unnamed')} — {item.get('id')}"
                        for item in unresolved_matches["results"]
                    ]
                    match_label = st.selectbox(
                        f"Select the {missing_entity} mentioned in your question",
                        match_labels,
                        key=f"qa_unresolved_{missing_entity}_choice",
                    )
                    selected_match = unresolved_matches["results"][match_labels.index(match_label)]
                    if missing_entity == "drug":
                        drug = {"id": selected_match["id"], "name": selected_match["name"]}
                    else:
                        disease = {"id": selected_match["id"], "name": selected_match["name"]}
                else:
                    st.info(f"Open Targets returned no {missing_entity} match for **{unresolved_term}**.")

            if disease:
                st.markdown(f"### Retrieved disease: {disease['name']}")
                st.markdown("**Local source: Hetionet v1.0**")
                local_gene_ids, local_gene_names = _disease_local_evidence(disease["id"])
                if local_gene_names:
                    st.markdown("Disease-associated genes recorded locally: " + format_list(local_gene_names, max_items=30))
                    answer_parts.append(f"Hetionet records {len(local_gene_names)} associated genes for {disease['name']}.")
                else:
                    st.info("Hetionet has no disease–gene relationships for this record.")
                    answer_parts.append("Hetionet returned no disease-associated genes for this record.")

                with st.spinner("Retrieving live Open Targets disease associations…"):
                    disease_hit, disease_error = _opentargets_for_name(disease["name"], "disease")
                _show_api_error(disease_error, "Open Targets")
                external_disease = None
                if disease_hit:
                    external_response = get_opentargets_disease(disease_hit["id"])
                    _show_api_error(external_response["error"], "Open Targets disease details")
                    external_disease = external_response["result"]
                if external_disease:
                    st.markdown(f"**Live source: Open Targets** · [{external_disease['name']}](https://platform.opentargets.org/disease/{external_disease['id']}/associations)")
                    if external_disease.get("description"):
                        st.write(external_disease["description"])
                    if external_disease.get("aliases"):
                        st.markdown("Alternative names: " + format_list(external_disease["aliases"], max_items=12))
                    target_rows = external_disease.get("targets", [])
                    if target_rows:
                        st.markdown("Associated targets and Open Targets scores (scores are not probabilities):")
                        st.dataframe(pd.DataFrame([
                            {"Target": row.get("symbol") or row.get("name") or row["id"], "ID": row.get("id"), "Score": round(row.get("score", 0), 4)}
                            for row in target_rows
                        ]), use_container_width=True, hide_index=True)
                        answer_parts.append(f"Open Targets returned target associations for {external_disease['name']}.")
                    if not local_gene_names and not target_rows:
                        st.info("No disease-associated genes were returned by either source.")
                elif not disease_error:
                    st.info("Open Targets did not return a disease match for this name.")

            if drug:
                st.markdown(f"### Retrieved medicine: {drug['name']}")
                profile = get_drug_profile(drug["id"])
                if profile:
                    st.markdown("**Local source: Hetionet v1.0**")
                    st.markdown("Recorded targets: " + format_list(profile["targets"], max_items=25))
                    st.markdown("Recorded indications: " + format_list(profile["treats"] + profile["palliates"], max_items=20))
                    answer_parts.append(f"Hetionet records {len(profile['targets'])} molecular targets for {drug['name']}.")
                with st.spinner("Retrieving live Open Targets medicine mechanisms…"):
                    drug_hit, drug_error = _opentargets_for_name(drug["name"], "drug")
                _show_api_error(drug_error, "Open Targets")
                external_drug = None
                if drug_hit:
                    external_response = get_opentargets_drug(drug_hit["id"])
                    _show_api_error(external_response["error"], "Open Targets medicine details")
                    external_drug = external_response["result"]
                if external_drug:
                    st.markdown(f"**Live source: Open Targets** · [{external_drug['name']}](https://platform.opentargets.org/drug/{external_drug['id']})")
                    if external_drug.get("trade_names"):
                        st.markdown("Trade names: " + format_list(external_drug["trade_names"], max_items=12))
                    if external_drug.get("mechanisms"):
                        st.markdown("Mechanisms: " + format_list(external_drug["mechanisms"], max_items=10))
                    ext_targets = external_drug.get("targets", [])
                    if ext_targets:
                        st.markdown("Open Targets mechanism-linked genes: " + format_list([target.get("approvedSymbol") or target.get("id") for target in ext_targets], max_items=20))

            if repurposing_question and disease and drug:
                local_overlap = _match_pair(drug["id"], disease["id"])
                external_symbols = set()
                if external_drug and external_disease:
                    drug_symbols = {str(item.get("approvedSymbol", "")).casefold() for item in external_drug.get("targets", []) if item.get("approvedSymbol")}
                    disease_symbols = {str(item.get("symbol", "")).casefold() for item in external_disease.get("targets", []) if item.get("symbol")}
                    external_symbols = drug_symbols & disease_symbols
                combined_overlap = sorted(set(local_overlap["genes"]) | external_symbols)
                st.markdown("### Drug–disease relationship check")
                if combined_overlap:
                    st.success("Shared target relationship(s) were found in the retrieved records: " + format_list(combined_overlap, max_items=20))
                    st.warning("This is a computational research lead based on target overlap only—not evidence of efficacy, a clinical recommendation, or an approved treatment.")
                else:
                    st.info("No shared drug-target / disease-target relationship was found in the records retrieved for this pair. No repurposing candidate is asserted.")

            if repurposing_question and disease and not drug:
                candidates = find_repurposing_candidates(disease["id"], top_n=5)
                st.markdown("### Hetionet computational research leads")
                if candidates is not None and not candidates.empty:
                    st.warning("These are unvalidated research leads ranked by connecting Hetionet genes; they are not approved treatment suggestions.")
                    st.dataframe(candidates[["rank", "drug_name", "gene_count", "connecting_genes"]], use_container_width=True, hide_index=True)
                    answer_parts.append(f"Hetionet returned {len(candidates)} candidate leads for further research.")
                else:
                    st.info("Hetionet returned no candidate leads for this disease. Open Targets gene associations alone do not establish a drug candidate, so none is inferred.")

            if not disease and not drug:
                st.warning("I could not identify a disease or medicine in local records. Provide its name in the context field; live matches will remain selectable suggestions.")
                search_term = explicit_context or unresolved_term
                if search_term:
                    entity_types = ["disease", "drug"] if context_type == "Auto-detect" else ["disease" if context_type == "Disease" else "drug"]
                    found_live_record = False
                    for entity in entity_types:
                        with st.spinner(f"Searching Open Targets for {entity} records…"):
                            response = search_opentargets(search_term, entity)
                        _show_api_error(response["error"], "Open Targets")
                        hits = response["results"]
                        if not hits:
                            continue
                        found_live_record = True
                        st.markdown(f"**Live Open Targets {entity} suggestions** — choose the intended record:")
                        labels = [f"{item.get('name', 'Unnamed')} — {item.get('id')}" for item in hits]
                        selection = st.selectbox(
                            f"Select a {entity} match",
                            labels,
                            key=f"qa_live_{entity}_choice",
                        )
                        selected_hit = hits[labels.index(selection)]
                        if entity == "disease":
                            detailed = get_opentargets_disease(selected_hit["id"])
                            _show_api_error(detailed["error"], "Open Targets disease details")
                            record = detailed["result"]
                            if record:
                                st.markdown(f"**Source: Open Targets** · [{record['name']}](https://platform.opentargets.org/disease/{record['id']}/associations)")
                                st.write(record.get("description") or "No disease description is available.")
                                if record.get("aliases"):
                                    st.markdown("Alternative names: " + format_list(record["aliases"], max_items=15))
                                targets = record.get("targets", [])
                                if targets:
                                    st.dataframe(pd.DataFrame([
                                        {"Target": row.get("symbol") or row.get("name") or row["id"], "Ensembl ID": row.get("id"), "Association score": round(row.get("score", 0), 4)}
                                        for row in targets
                                    ]), use_container_width=True, hide_index=True)
                                else:
                                    st.info("No disease-associated targets were returned by Open Targets.")
                                _render_pubmed(f'("{record["name"]}"[Title/Abstract]) AND (gene OR target)', "Disease PubMed references")
                        else:
                            detailed = get_opentargets_drug(selected_hit["id"])
                            _show_api_error(detailed["error"], "Open Targets medicine details")
                            record = detailed["result"]
                            if record:
                                st.markdown(f"**Source: Open Targets** · [{record['name']}](https://platform.opentargets.org/drug/{record['id']})")
                                st.write(record.get("description") or "No medicine description is available.")
                                if record.get("trade_names"):
                                    st.markdown("Trade names: " + format_list(record["trade_names"], max_items=15))
                                if record.get("mechanisms"):
                                    st.markdown("Mechanisms: " + format_list(record["mechanisms"], max_items=10))
                                if record.get("targets"):
                                    st.markdown("Mechanism-linked targets: " + format_list([target.get("approvedSymbol") or target.get("id") for target in record["targets"]], max_items=20))
                                if record.get("indications"):
                                    st.markdown("Indications in Open Targets: " + format_list(record["indications"], max_items=20))
                                _render_pubmed(f'("{record["name"]}"[Title/Abstract]) AND (target OR mechanism)', "Medicine PubMed references")
                    if not found_live_record:
                        st.info("No matching disease or medicine information was returned by Open Targets. Try another spelling or check PubMed directly.")
                else:
                    st.info("No disease or medicine name could be extracted. Enter a name in the context field to search Open Targets.")

            # Only query PubMed when an entity was identified. References are
            # supporting search results, not proof that a relationship is causal.
            if disease and drug:
                pubmed_query = pubmed_pair_query(drug["name"], disease["name"])
                _render_pubmed(pubmed_query, "Drug–disease PubMed references")
            elif disease:
                _render_pubmed(f'("{disease["name"]}"[Title/Abstract]) AND (gene OR target)', "Disease PubMed references")
            elif drug:
                _render_pubmed(f'("{drug["name"]}"[Title/Abstract]) AND (target OR mechanism)', "Medicine PubMed references")

            if answer_parts:
                st.markdown("### Evidence-based summary")
                st.markdown(" ".join(answer_parts))
            st.caption("Retrieved-source summary only. PubMed matches are literature search results; titles alone do not establish efficacy or causality.")

st.markdown("---")
st.caption("Local source: Hetionet v1.0. Live sources: Open Targets Platform GraphQL API and NCBI PubMed E-utilities. Research/education only; not medical advice.")
