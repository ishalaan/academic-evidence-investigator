# Academic Evidence Investigator

## Purpose and overview

Academic Evidence Investigator is an LLM-powered research-support prototype for postgraduate evidence gathering. It turns a research question into a structured briefing with a summary, findings, limitations and traceable references. It supports academic judgement; it does not provide an exhaustive systematic review.

The Flask interface accepts a question and displays workflow progress. LangGraph coordinates planning, retrieval, processing, criticism and reporting through shared state:

1. The Planner creates focused searches using **Qwen/Qwen3-8B via Hugging Face**.
2. Retrieval searches **Crossref and Semantic Scholar** independently.
3. Processing validates, deduplicates and filters records, then obtains **PDF full text, HTML article text or an abstract fallback**. Records without usable text remain visible as metadata rather than supporting synthesis.
4. Local **sentence-transformer embeddings** and **FAISS** select relevant passages alongside deterministic relevance controls. Source locations remain attached to evidence.
5. The Critic assesses sufficiency and can request replanning, retaining earlier evidence. A three-cycle limit bounds the search.
6. The Reporter produces a briefing; references are rendered from retrieved metadata. **SQLite** stores reports and audit information for browser review.

## Installation and dependencies

Requirements: **Python 3.11+**, Git, internet access for retrieval and hosted inference, and a Hugging Face token with access to the configured inference service. The supplied final test run used Python 3.14.0 on Windows. Local embeddings require an initial model download and sufficient local memory.

Clone the submitted GitHub repository, or extract the submitted source, and open a terminal in its root folder. For a clone, replace the placeholder with the submitted repository URL:

```text
git clone <repository-url>
cd academic-evidence-investigator
python -m venv venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\venv\Scripts\Activate.ps1
```

```sh
# macOS / Linux
source venv/bin/activate
```

Install application and test dependencies:

```text
python -m pip install -e ".[dev]"
```

`pyproject.toml` declares the dependencies; `requirements.txt` also lists them. SQLite is supplied through Python. No separate database server or local Qwen installation is required.

## Configuration

Create a file named **`.env`** in the project root:

```dotenv
HF_TOKEN=your_hugging_face_token
# Optional: authenticated Semantic Scholar access
SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key
# Optional: enables Unpaywall open-access location lookup
UNPAYWALL_EMAIL=your_email_address
```

Omit optional entries when unused. Crossref needs no API key for this workflow. The active model is set in `src/package/services/llm.py`; search limits are in `src/package/config.py`. Hosted inference depends on provider availability and account credits. Keep `.env`, credentials and generated runtime data out of Git/GitHub.

## Run the application

With the environment activated, run:

```text
python app.py
```

The application initialises SQLite and opens [http://127.0.0.1:5000](http://127.0.0.1:5000). Enter a research question, submit it, and review progress, the resulting briefing, ranked sources and audit information. Stop the server with `Ctrl+C`. The launcher uses Flask's development server with debugging enabled and is intended for local demonstration.

## Tests and current status

Run all Python tests from the project root:

```text
python -m pytest
```

For verbose output or an optional coverage report:

```text
python -m pytest -v
python -m pytest --cov=package --cov-report=term-missing
```

**Final supplied test result: 263 Python tests passed in 25.13 seconds**, covering unit, integration and functional tests. This is the recorded project result, not a new execution performed for this README edit. Coverage includes validation, deduplication, retrieval failures, PDF/HTML extraction and fallback, embeddings, workflow routing, citation handling, persistence and Flask behaviour. Controlled test responses make failure cases reproducible; passing tests do not guarantee live API availability or factual correctness of every generated report.

Testing and remediation addressed:

- **Service failures:** independent retrieval sources, bounded retries and clearer provider diagnostics; the active inference model is Qwen3-8B.
- **Evidence access and relevance:** PDF-to-HTML-to-abstract fallback, article identity checks, duplicate-version handling and semantic passage selection.
- **Report reliability:** metadata-derived references, citation normalisation, targeted grounding checks, bounded section retries and context-budget controls. Remaining quality weaknesses can be exposed as review notes.
- **Traceability and interface:** persisted workflow decisions, safe progress/error messages and source-format-specific evidence locations.

Execution screenshots, sample outputs and test-tool output belong in `evidence/`. Git history and the GitHub repository document incremental development and retain the final submission.

## Project structure

```text
app.py                         Local application entry point
pyproject.toml / requirements.txt  Installation and dependency declarations
src/package/
  agents/                      Planner, retrieval, critic and reporter
  workflow/                    Shared state, graph and routing
  services/                    Inference, academic APIs and content retrieval
  processing/ / rag/           Validation, ranking and passage retrieval
  storage/                     SQLite persistence and audit records
  prompts/                     Agent instructions
  config.py / schemas.py / web.py  Configuration, validation and web routes
templates/ / static/            HTML, CSS and JavaScript interface
tests/                         Unit, integration, functional tests and fixtures
data/                          Local runtime data
evidence/                      Screenshots, test results and sample outputs
```

## Key design decisions

- **Explicit agent workflow:** LangGraph makes conditional replanning and termination inspectable. Planning followed by tool use is informed by ReAct (Yao et al., 2023), without claiming an exact reproduction.
- **Validated boundaries:** Pydantic validates plans, papers and agent outputs; deterministic code handles metadata, filtering and storage to improve testability and reduce unnecessary model dependence.
- **Retrieval-grounded synthesis:** PDF/HTML passages and abstract fallback give the model identifiable evidence, following the RAG principle (Lewis et al., 2020). Local `all-MiniLM-L6-v2` embeddings with FAISS improve passage selection; lexical controls remain part of the hybrid approach. An explicitly recorded lexical fallback is used if embeddings cannot load.
- **Bounded evidence and generation:** passage limits and section-level context budgets control input size, reflecting long-context reliability concerns (Liu et al., 2024). These limits can omit relevant material.
- **Traceable output:** metadata-derived references, source locators and audit records support human checking. Validation reduces hallucination risk but cannot eliminate it (Ji et al., 2023).
- **Simple local deployment:** Flask with HTML/CSS/JavaScript and SQLite provides an inspectable demonstration without a separate frontend build or database service. Behavioural and failure-case tests complement successful-path testing (Ribeiro et al., 2020).

## Limitations and responsible use

- **Coverage and reliability:** API coverage, rate limits, missing abstracts, inaccessible publications and model availability affect results. PDF extraction has no OCR; HTML extraction may reject unusual or JavaScript-only layouts. Ranking scores and Critic decisions are not validated measures of research quality.
- **Legal:** respect source licences, API terms, copyright and access controls. Public accessibility does not itself grant redistribution rights. The retrieval workflow does not bypass logins, paywalls or CAPTCHAs.
- **Social and ethical:** database, language and model biases can skew evidence; unequal connectivity and inference access affect usability. Users must inspect original sources and review unsupported or overstated claims before academic use.
- **Privacy and professional practice:** research questions and selected evidence are sent to hosted inference; avoid confidential or personal data. Protect credentials, retain reproducible test evidence, disclose AI assistance under institutional rules and acknowledge external work. Git/GitHub supports version control and development accountability.

## External technology acknowledgements

The implementation uses **Qwen3-8B** from the Qwen team through **Hugging Face** (`huggingface-hub`); **LangGraph** orchestration; **Pydantic** validation; **Flask** with HTML/CSS/JavaScript; **SQLite** storage; **Crossref** and **Semantic Scholar** APIs, with optional **Unpaywall** lookup; **Sentence Transformers** and `all-MiniLM-L6-v2` embeddings; **FAISS** (`faiss-cpu`) vector search; **PyMuPDF** PDF extraction; and **Beautiful Soup** HTML parsing. Supporting dependencies are **Requests**, **HTTPX**, **truststore**, **pandas** and **python-dotenv**. **pytest** and **pytest-cov** support testing; **Git and GitHub** support version control and submission. These external components remain subject to their respective licences and service terms.

## Academic references

Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., Ishii, E., Bang, Y., Madotto, A. and Fung, P. (2023) ‘Survey of hallucination in natural language generation’, *ACM Computing Surveys*, 55(12), article 248, pp. 1–38. Available at: [https://doi.org/10.1145/3571730](https://doi.org/10.1145/3571730) (Accessed: 16 September 2026).

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W.-T., Rocktäschel, T., Riedel, S. and Kiela, D. (2020) ‘Retrieval-augmented generation for knowledge-intensive NLP tasks’, *Advances in Neural Information Processing Systems*, 33, pp. 9459–9474. Available at: [NeurIPS proceedings](https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html) (Accessed: 16 September 2026).

Liu, N.F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F. and Liang, P. (2024) ‘Lost in the middle: how language models use long contexts’, *Transactions of the Association for Computational Linguistics*, 12, pp. 157–173. Available at: [https://doi.org/10.1162/tacl_a_00638](https://doi.org/10.1162/tacl_a_00638) (Accessed: 16 September 2026).

Ribeiro, M.T., Wu, T., Guestrin, C. and Singh, S. (2020) ‘Beyond accuracy: behavioral testing of NLP models with CheckList’, in *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics*. Online, 5–10 July. Association for Computational Linguistics, pp. 4902–4912. Available at: [https://doi.org/10.18653/v1/2020.acl-main.442](https://doi.org/10.18653/v1/2020.acl-main.442) (Accessed: 16 September 2026).

Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K. and Cao, Y. (2023) ‘ReAct: synergizing reasoning and acting in language models’, *The Eleventh International Conference on Learning Representations*. Kigali, Rwanda, 1–5 May. Available at: [OpenReview](https://openreview.net/forum?id=WE_vluYUL-X) (Accessed: 16 September 2026).
