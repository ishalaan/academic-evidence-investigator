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

Install Python 3.11 or later and Git. Live use also requires internet access and a Hugging Face token with access to the configured inference service. The recorded test environment was Windows with Python 3.14.0; macOS and Linux commands are provided below, but those platforms have not been verified in the submitted test evidence.

### Get the source

Open a terminal in the folder where you want to save the project. On Windows, use **Command Prompt (CMD)**; if PowerShell is already open, type `cmd` first. Run:

```text
git clone git@github.com:ishalaan/academic-evidence-investigator.git
```

The SSH command requires a key linked to a GitHub account with repository access. If SSH is not configured, use this HTTPS command instead:

```text
git clone https://github.com/ishalaan/academic-evidence-investigator.git
```

If using the submitted source archive or an existing checkout, skip cloning and open a terminal in `path/to/academic-evidence-investigator/`, replacing `path/to/` with the location where you saved the project. This is the project root containing `app.py` and `pyproject.toml`. In the commands below, replace `path/to/academic-evidence-investigator/` with the actual project location before running them.

### Windows — Command Prompt (CMD)

```bat
cd /d "path/to/academic-evidence-investigator/"
python -m venv venv
venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
```

If Windows recognises `py` instead of `python`, use `py -m venv venv` for the first command. After activation, use `python` as shown. No PowerShell execution-policy change is needed.

### macOS — Terminal

```sh
cd "path/to/academic-evidence-investigator/"
python3 -m venv venv
source venv/bin/activate
python -m pip install -e ".[dev]"
```

### Linux — Terminal (Bash)

```sh
cd "path/to/academic-evidence-investigator/"
python3 -m venv venv
source venv/bin/activate
python -m pip install -e ".[dev]"
```

If Linux reports that `venv` is unavailable, install the venv package for your Python version through your distribution's package manager, then retry.

Create the environment once. When returning to the project, open a terminal in its root folder and repeat only the activation command for your operating system.

`pyproject.toml` declares application and development dependencies; `requirements.txt` also lists them. SQLite is included with Python. Qwen runs through hosted inference, while the embedding model runs locally and downloads on first use. No separate database server is required.

## Configuration

Create a plain-text file named **`.env`** in the project root, alongside `app.py`. Replace the example token with your own credentials. On Windows, make sure the filename is `.env`, not `.env.txt`:

```dotenv
HF_TOKEN=your_hugging_face_token
# Optional: authenticated Semantic Scholar access
SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key
# Optional: enables Unpaywall open-access location lookup
UNPAYWALL_EMAIL=your_email_address
```

Omit optional entries when unused. Crossref needs no API key for this workflow. The active model is set in `src/package/services/llm.py`; search limits are in `src/package/config.py`. Hosted inference depends on provider availability and account credits. Keep `.env`, credentials and generated runtime data out of Git/GitHub.

## Run the application

After completing configuration, run this from the project root in the activated environment on Windows CMD, macOS or Linux:

```text
python app.py
```

The application initialises SQLite and opens [http://127.0.0.1:5000](http://127.0.0.1:5000). Enter a research question, submit it, and review progress, the resulting briefing, ranked sources and audit information. Stop the server with `Ctrl+C`. The launcher uses Flask's development server with debugging enabled and is intended for local demonstration.

## Tests and current status

Run all Python tests from the project root in the activated environment on any of the three operating systems. Stop the application first, or use another terminal with the same environment activated:

```text
python -m pytest
```

For verbose output or an optional coverage report:

```text
python -m pytest -v
python -m pytest --cov=package --cov-report=term-missing
```

**Final recorded result: 263 Python tests passed**, across unit, integration and functional tests. The saved output is in [evidence/test_results/05_final_pytest_results.txt](evidence/test_results/05_final_pytest_results.txt). Coverage includes validation, deduplication, retrieval failures, PDF/HTML extraction and fallback, embeddings, workflow routing, citation handling, persistence and Flask behaviour. Controlled test responses make failure cases reproducible; passing tests do not guarantee live API availability or factual correctness of every generated report.

Testing and remediation addressed:

- **Service failures:** independent retrieval sources, bounded retries and clearer provider diagnostics; the active inference model is Qwen3-8B.
- **Evidence access and relevance:** PDF-to-HTML-to-abstract fallback, article identity checks, duplicate-version handling and semantic passage selection.
- **Report reliability:** metadata-derived references, citation normalisation, targeted grounding checks, bounded section retries and context-budget controls. In normal operation, unresolved quality weaknesses are recorded as review notes rather than always blocking completion; users must check these notes and the cited evidence.
- **Traceability and interface:** persisted workflow decisions, safe progress/error messages and source-format-specific evidence locations.

Execution screenshots are in `evidence/screenshots/demo/`; debugging and final-test screenshots are in `evidence/screenshots/debugging/`. Saved reports and sample outputs are in `evidence/saved_reports/` and `evidence/sample_outputs/`. Git history records incremental development, with the source maintained on GitHub.

## Project structure

| Path | Purpose |
| --- | --- |
| `app.py` | Starts the local application. |
| `pyproject.toml`, `requirements.txt` | Declare installation settings and dependencies. |
| `src/package/agents/` | Planner, retrieval, critic and reporter logic. |
| `src/package/workflow/` | Shared state and workflow routing. |
| `src/package/services/` | Model access, academic APIs and content retrieval. |
| `src/package/processing/` | Validation, deduplication, ranking and semantic passage selection. |
| `src/package/rag/` | Prepares retrieved evidence within model context limits. |
| `src/package/storage/` | SQLite persistence and audit records. |
| `src/package/prompts/` | Agent prompt templates. |
| `src/package/config.py` | Environment settings and search limits. |
| `src/package/schemas.py` | Structured data models. |
| `src/package/web.py` | Flask routes and request handling. |
| `templates/`, `static/` | Browser interface and styling. |
| `tests/` | Unit, integration and functional tests, with fixtures. |
| `data/` | Local runtime data. |
| `evidence/` | Test results, screenshots, saved reports and sample outputs. |

## Key design decisions

- **Workflow control:** LangGraph makes conditional replanning and termination inspectable. Planning followed by tool use is informed by ReAct (Yao et al., 2023), without claiming an exact reproduction.
- **Structured data:** Pydantic validates plans, papers and agent outputs; deterministic code handles metadata, filtering and storage to improve testability and reduce unnecessary model dependence.
- **Evidence selection:** PDF/HTML passages and abstract fallback give the model identifiable evidence, following the RAG principle (Lewis et al., 2020). Local `all-MiniLM-L6-v2` embeddings with FAISS select passages by meaning alongside lexical relevance and paper-rank signals. An explicitly recorded lexical fallback is used if embeddings cannot load.
- **Context limits:** passage limits and section-level context budgets control input size, reflecting long-context reliability concerns (Liu et al., 2024). These limits can omit relevant material.
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

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W.-T., Rocktäschel, T., Riedel, S. and Kiela, D. (2020) ‘Retrieval-augmented generation for knowledge-intensive NLP tasks’, *Advances in Neural Information Processing Systems*, 33, pp. 9459–9474. Available at: [https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html](https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html) (Accessed: 16 September 2026).

Liu, N.F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F. and Liang, P. (2024) ‘Lost in the middle: how language models use long contexts’, *Transactions of the Association for Computational Linguistics*, 12, pp. 157–173. Available at: [https://doi.org/10.1162/tacl_a_00638](https://doi.org/10.1162/tacl_a_00638) (Accessed: 16 September 2026).

Ribeiro, M.T., Wu, T., Guestrin, C. and Singh, S. (2020) ‘Beyond accuracy: behavioral testing of NLP models with CheckList’, in *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics*. Online, 5–10 July. Association for Computational Linguistics, pp. 4902–4912. Available at: [https://doi.org/10.18653/v1/2020.acl-main.442](https://doi.org/10.18653/v1/2020.acl-main.442) (Accessed: 16 September 2026).

Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K. and Cao, Y. (2023) ‘ReAct: synergizing reasoning and acting in language models’, *The Eleventh International Conference on Learning Representations*. Kigali, Rwanda, 1–5 May. Available at: [https://openreview.net/forum?id=WE_vluYUL-X](https://openreview.net/forum?id=WE_vluYUL-X) (Accessed: 16 September 2026).
