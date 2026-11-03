# Intelligent Drug Repurposing Research Assistant

An educational biomedical research application that explores **potential drug repurposing hypotheses** by analysing drug–gene–disease relationships in the Hetionet knowledge graph and retrieving supporting public biomedical records.

> **Important:** This application is a research and learning tool, not a medical device. Its outputs are computational research leads, not validated treatments or medical advice. Do not use them to make treatment decisions.

## Features

- **Disease Search:** Search the local Hetionet dataset for diseases and explore candidate compounds connected through shared molecular targets.
- **Drug Profile:** Review available molecular targets, recorded disease indications, drug classes and side-effect relationships.
- **Graph Explorer:** Build interactive drug–gene–disease network visualisations.
- **Biomedical Research Assistant:** Search local records and retrieve additional disease, drug and publication information from public Open Targets and PubMed services.
- **Medicine-label OCR:** Upload a medicine-label image to attempt text extraction. Always verify the extracted medicine name; OCR can make mistakes.

## How the analysis works

The local repurposing workflow uses a two-hop relationship:

```text
Drug ── binds ──> Gene ── associated with ──> Disease
```

1. Find genes associated with the selected disease in Hetionet.
2. Find compounds connected to those genes.
3. Exclude compounds already recorded as treating or palliating that disease in the local dataset.
4. Rank remaining candidates using the number of distinct shared genes.

This is a transparent graph-based prioritisation method. A higher shared-gene count is **not** a probability of success, proof of efficacy, or clinical validation.

## Technology stack

- Python
- Streamlit
- Pandas
- NetworkX
- PyVis
- Requests
- Pillow and pytesseract (for image text extraction)

## Data and external sources

- **Hetionet v1.0:** Local biomedical knowledge graph used for the core relationship analysis. The setup script downloads the node and edge files from the [Hetionet GitHub repository](https://github.com/hetio/hetionet).
- **Open Targets Platform:** Public biomedical target and drug information retrieved by the research assistant. [Website](https://platform.opentargets.org/)
- **PubMed:** Biomedical literature search results. [Website](https://pubmed.ncbi.nlm.nih.gov/)

External services require an internet connection and may return incomplete results or be temporarily unavailable. Results are displayed with their source where available.

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/Tanishka80/Intelligent-Drug-Repurposing-System.git
cd Intelligent-Drug-Repurposing-System
```

### 2. Create and activate a virtual environment (recommended)

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Download and prepare the dataset

```bash
python setup_data.py
```

This downloads Hetionet v1.0 node and edge files, filters the relationship types used by the application, and writes the processed files into the local `data/` directory. An internet connection is required. The data directory is excluded from Git to avoid committing large dataset files.

### 5. Start the application

```bash
python -m streamlit run app.py
```

Open the local URL printed in the terminal (usually `http://localhost:8501`).

## OCR note

The Python package `pytesseract` is listed in the dependencies. Image text extraction also requires the **Tesseract OCR engine** to be installed separately and available to the application. OCR output should always be checked against the original medicine label.

## Project structure

```text
.
├── app.py
├── setup_data.py
├── requirements.txt
├── pages/
│   ├── 1_Disease_Search.py
│   ├── 2_Drug_Profile.py
│   ├── 3_Graph_Explorer.py
│   └── 4_Research_Assistant.py
├── src/
│   ├── biomedical_api.py
│   ├── data_loader.py
│   ├── repurposing.py
│   └── utils.py
├── lib/
└── .streamlit/
```

## Limitations

- Hetionet and external biomedical databases have finite coverage; a search may not return a match for every medicine or disease.
- External API availability, response times and returned records can vary.
- OCR may misread text, especially on unclear or low-quality images.
- Graph connections and candidate rankings are exploratory evidence only. They do not establish safety, effectiveness, dosage, approval or suitability for any person.
- The research assistant retrieves and organises records and relationship evidence; it does not use a configured generative AI model to establish new medical facts.

## Intended use

This project was developed as an academic software and biomedical-informatics prototype to demonstrate knowledge-graph analysis, public biomedical data retrieval and interactive research workflows. It is intended for educational and research exploration only.

---

**Repository:** [Tanishka80/Intelligent-Drug-Repurposing-System](https://github.com/Tanishka80/Intelligent-Drug-Repurposing-System)
