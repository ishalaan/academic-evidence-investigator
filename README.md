# Academic Evidence Investigator

## Purpose

The Academic Evidence Investigator is an LLM-powered multi-agent system designed to support postgraduate academic research and structured evidence gathering.

The system accepts a high-level research question, creates a search plan, retrieves relevant academic metadata, processes and evaluates the evidence, and produces a structured research briefing containing a summary, findings, limitations, and traceable sources.

The application is intended as a research-support tool rather than a replacement for academic judgement. It does not claim to provide exhaustive literature coverage or definitive research-gap identification.

---

## High-Level Overview

The implemented system uses a cooperating multi-agent architecture.

The main workflow is:

1. A user enters a research question through the Flask web interface.
2. The Planner Agent interprets the goal and creates focused academic search queries.
3. The Retrieval Agent searches external academic sources.
4. Retrieved papers are validated, deduplicated, filtered, and ranked.
5. The Critic Agent evaluates whether the evidence is sufficiently relevant and balanced.
6. If necessary, the system replans and performs another retrieval cycle.
7. The Reporter Agent generates a structured research briefing from the accepted evidence.
8. The report is saved to SQLite and displayed in the browser.

The workflow is orchestrated using LangGraph and shared state.

---

## Architecture

The system contains four main agent responsibilities.

### Planner Agent

The Planner Agent receives the research question and creates a focused search plan.

It can also use feedback from the Critic Agent when additional evidence is required.

### Retrieval Agent

The Retrieval Agent executes the current search plan using:

- Semantic Scholar
- Crossref

The two sources are handled independently so that failure of one API does not terminate the complete research workflow.

Semantic Scholar is treated as an optional source because live testing showed occasional rate limiting, server errors, and timeouts.

Crossref acts as a reliable fallback source.

### Evidence Analysis / Critic Agent

The Critic Agent evaluates whether the retrieved evidence is sufficiently relevant, useful, and balanced.

If the evidence is weak, the workflow can route back to the Planner Agent for another search cycle.

A maximum search-cycle limit prevents uncontrolled loops.

### Reporting Agent

The Reporting Agent synthesises the accepted evidence into a structured research briefing.

The LLM is not allowed to generate bibliography metadata independently.

The final source list is produced from the retrieved `Paper` objects so titles, authors, DOI values, URLs, and publication years remain traceable to the original metadata.

---

## Technologies

The main technologies used are:

- Python 3.11+
- LangGraph
- Hugging Face Inference API
- Qwen/Qwen3-8B
- Flask
- Pydantic
- Requests
- Semantic Scholar Academic Graph API
- Crossref REST API
- SQLite
- PyTest
- PyTest-Cov
- python-dotenv
- Git and GitHub

The project uses a conventional `src` package layout.

---

## Installation

### 1. Clone the repository

    git clone <repository-url>
    cd academic-evidence-investigator

### 2. Create a virtual environment

Windows:

    python -m venv venv
    venv\Scripts\activate

macOS / Linux:

    python -m venv venv
    source venv/bin/activate

### 3. Install the project and development dependencies

    pip install -e ".[dev]"

Alternatively, dependencies are also listed in `requirements.txt`.

---

## Configuration

Create a `.env` file in the project root.

Example:

    HF_TOKEN=your_hugging_face_token
    SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key

A template is provided in:

    .env.example

### Hugging Face

`HF_TOKEN` is required for live LLM inference.

The implementation currently uses:

    Qwen/Qwen3-8B

The model is centralised in the LLM service so that it can be replaced without changing the overall agent architecture.

### Semantic Scholar

`SEMANTIC_SCHOLAR_API_KEY` is optional but recommended.

The application can continue without Semantic Scholar because the Retrieval Agent handles source-specific failures and continues using Crossref.

The Semantic Scholar integration uses:

    GET /graph/v1/paper/search

Requested metadata fields include:

- title
- authors
- abstract
- year
- URL
- external identifiers such as DOI

### Crossref

Crossref does not require an API key for the implemented search workflow.

### Security

The `.env` file must not be committed to GitHub.

API keys and tokens should never be stored directly in source code.

---

## Running the Application

Activate the virtual environment and run:

    python app.py

The Flask application starts locally and the default browser should open automatically at:

    http://127.0.0.1:5000

The form contains an example research question that can be replaced with any suitable research goal.

When the user submits the form:

1. the submit button is disabled
2. a loading screen is displayed
3. the multi-agent workflow executes
4. the generated research report is displayed
5. the report is saved to SQLite

---

## Running the Tests

Run the complete automated test suite with:

    pytest

The final implementation currently passes:

    26 automated tests

The test suite includes:

- unit tests
- integration tests
- functional tests

Testing covers areas including:

- validation
- deduplication
- relevance ranking
- processing pipeline
- Planner output
- Critic output
- Critic routing
- Retrieval Agent behaviour
- Semantic Scholar response normalisation
- Crossref response normalisation
- Reporter output
- database persistence
- Flask page behaviour
- LLM client configuration

Testing evidence is stored under:

    evidence/test_results/

Execution screenshots are stored under:

    evidence/screenshots/

---

## Project Structure

    academic-evidence-investigator/
    ├── app.py
    ├── README.md
    ├── requirements.txt
    ├── pyproject.toml
    ├── .env.example
    ├── src/
    │   └── package/
    │       ├── __init__.py
    │       ├── config.py
    │       ├── schemas.py
    │       ├── web.py
    │       ├── agents/
    │       │   ├── planner.py
    │       │   ├── retrieval.py
    │       │   ├── critic.py
    │       │   └── reporter.py
    │       ├── workflow/
    │       │   ├── state.py
    │       │   ├── nodes.py
    │       │   └── graph.py
    │       ├── services/
    │       │   ├── llm.py
    │       │   ├── prompts.py
    │       │   ├── json_utils.py
    │       │   ├── semantic_scholar.py
    │       │   └── crossref.py
    │       ├── processing/
    │       │   ├── pipeline.py
    │       │   ├── deduplication.py
    │       │   ├── ranking.py
    │       │   └── validation.py
    │       ├── storage/
    │       │   └── database.py
    │       └── prompts/
    │           ├── planner.txt
    │           ├── critic.txt
    │           └── reporter.txt
    ├── templates/
    │   ├── index.html
    │   └── report.html
    ├── static/
    │   └── styles.css
    ├── tests/
    │   ├── unit/
    │   ├── integration/
    │   ├── functional/
    │   └── fixtures/
    ├── data/
    └── evidence/
        ├── screenshots/
        ├── test_results/
        └── sample_outputs/

---

## Key Design Decisions

### LangGraph orchestration

LangGraph was selected because the system requires explicit state transitions, conditional routing, and controlled replanning.

A simple linear script would make it harder to represent the Critic-to-Planner feedback loop.

### Separation of LLM and deterministic processing

The LLM is used for tasks that require interpretation and synthesis:

- planning
- evidence criticism
- report generation

Deterministic Python processing is used for:

- validation
- deduplication
- filtering
- ranking
- persistence

This separation reduces unnecessary LLM dependence and makes low-level evidence processing easier to test and explain.

### Structured Pydantic models

Pydantic models are used to validate structured agent outputs.

This reduces the risk of invalid state being passed between agents and provides a consistent internal representation for plans, papers, critic decisions, and reports.

### Retrieval-source independence

Semantic Scholar and Crossref are called independently.

This prevents one external service from becoming a single point of failure.

If Semantic Scholar fails, the workflow can continue using Crossref.

### Evidence accumulation during replanning

Papers retrieved during earlier search cycles are retained.

This means replanning expands the evidence base instead of discarding previously retrieved material.

### Deterministic relevance filtering

Retrieved papers are ranked using deterministic question-to-paper term matching.

Generic LLM terms are distinguished from domain-specific terms derived from the user's research question.

This prevents broad LLM records from ranking highly when they do not match the selected research domain.

### Evidence-set limit

Only the strongest ranked papers are retained for Critic and Reporter processing.

This reduces irrelevant context and keeps the final briefing concise.

### Bibliographic traceability

The Reporting Agent is instructed not to invent bibliography metadata or author-year citations.

The final source list is generated from retrieved metadata rather than from free-form LLM output.

### SQLite persistence

SQLite was selected for the prototype because it is lightweight, requires no external database server, and is sufficient for local demonstration and assessment.

A larger deployment could migrate to PostgreSQL or another managed database.

---

## Testing and Remediation

The implementation was developed iteratively and several issues were identified during testing.

### Hugging Face model availability

The originally proposed Qwen2.5 model was not available through the active serverless inference provider.

The model service was therefore kept configurable and the implementation was moved to `Qwen/Qwen3-8B`.

### Semantic Scholar reliability

Live Semantic Scholar testing produced HTTP 429 responses, HTTP 500 responses, and read timeouts.

The Retrieval Agent was changed so Semantic Scholar failure does not terminate the workflow.

Crossref continues supplying academic metadata when Semantic Scholar is unavailable.

### Test-double mismatch

After Semantic Scholar response-status handling was added, the integration-test `FakeResponse` object no longer matched the production response interface.

The test double was updated to include the required status-code behaviour.

### Relevance-filter test failures

Introducing stricter relevance filtering caused earlier tests using generic placeholder paper titles to fail.

The production filtering rules were retained and the test fixtures were updated to use realistic relevant and irrelevant papers.

### Noisy Crossref results

Crossref returned some unsuitable records such as figures, tables, and front matter.

Deterministic validation rules were added to remove these records before ranking.

### Duplicate preprint versions

Versioned preprint DOIs such as `/v1` and `/v2` initially appeared as separate evidence.

DOI normalisation was extended so different versions of the same underlying work are deduplicated.

### LLM-generated citation details

The Reporter initially generated publication years that were not present in retrieved metadata.

Author-year citations were removed from free-form report generation and bibliographic traceability was moved to deterministic source rendering.

After remediation, the complete automated test suite passes all 26 tests.

---

## Known Limitations

The system is a prototype and has several limitations.

### Retrieval coverage

The final evidence set depends on the metadata returned by Semantic Scholar and Crossref.

The system does not claim exhaustive literature coverage.

### Semantic Scholar availability

Semantic Scholar may be rate-limited, unavailable, or slow during live execution.

The application falls back to Crossref when this occurs.

### Metadata quality

Some academic records contain missing abstracts, publication years, or author information.

The system avoids inventing missing bibliography metadata.

### Relevance ranking

The implemented ranking is deterministic and explainable but is based primarily on token overlap rather than embedding-based semantic similarity.

This improves transparency but may miss conceptually relevant papers that use different terminology.

### LLM reliability

The Planner, Critic, and Reporter remain dependent on generative-model behaviour.

Structured validation and source grounding reduce risk but cannot eliminate hallucination or interpretation errors.

### Evidence sufficiency

The Critic Agent evaluates whether the retrieved evidence is sufficient, but this remains partly an LLM judgement rather than a formally validated academic-review metric.

### Prototype deployment

The current Flask and SQLite implementation is designed for local demonstration rather than production-scale multi-user deployment.

---

## Legal, Social, Ethical and Professional Considerations

### Legal

The application depends on external services and must respect their API terms, licensing conditions, and rate limits.

Academic metadata and source links are retained rather than republishing full copyrighted publications.

API credentials are stored privately through environment variables.

### Social

Access to LLM-powered research tools is not equal across all students, institutions, or regions.

Differences in digital access and AI literacy may influence who benefits from systems of this kind.

### Ethical

LLMs may hallucinate, introduce bias, misrepresent evidence, or produce misleading conclusions.

The system therefore:

- keeps retrieved source metadata attached to reports
- avoids generating bibliography metadata independently
- exposes limitations
- uses deterministic preprocessing
- requires human academic judgement

The system is intended to assist rather than replace researchers.

### Professional

Professional use requires:

- reproducible testing
- transparent source handling
- secure credential management
- clear disclosure of system limitations
- human oversight
- responsible interpretation of generated findings

The implementation therefore maintains a clear separation between retrieved metadata, deterministic processing, and LLM-generated synthesis.

---

## External Libraries, Frameworks, Models and APIs

This project uses the following external technologies:

### LangGraph

Used for agent workflow orchestration, shared state, conditional routing, and replanning.

### Hugging Face

Used to access the configured LLM through the Hugging Face inference client.

### Qwen/Qwen3-8B

Used as the active language model for planning, evidence criticism, and report generation.

### Flask

Used to provide the browser-based demonstration interface.

### Pydantic

Used for structured data validation between agents.

### Requests

Used for HTTP communication with external academic APIs.

### Semantic Scholar Academic Graph API

Used as an academic retrieval source where available.

### Crossref REST API

Used to retrieve scholarly publication metadata and DOI information.

### SQLite

Used to persist completed research reports locally.

### PyTest and PyTest-Cov

Used for automated unit, integration, and functional testing.

---

## Academic References

The following academic concepts informed the design and implementation.

Bommasani, R., Hudson, D.A., Adeli, E., Altman, R., Arora, S., von Arx, S., Bernstein, M.S., Bohg, J., Bosselut, A., Brunskill, E. et al. (2021) ‘On the opportunities and risks of foundation models’. Stanford Center for Research on Foundation Models. Available at: https://crfm.stanford.edu/report.html (Accessed: 9 September 2026).

Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., Ishii, E., Bang, Y.J., Madotto, A. and Fung, P. (2023) ‘Survey of hallucination in natural language generation’, ACM Computing Surveys, 55(12), pp. 1–38. Available at: https://doi.org/10.1145/3571730 (Accessed: 9 September 2026).

Laux, J. (2024) ‘Institutionalised distrust and human oversight of artificial intelligence: towards a democratic design of AI governance under the European Union AI Act’, AI & Society, 39(6), pp. 2853–2866. Available at: https://doi.org/10.1007/s00146-023-01777-z (Accessed: 9 September 2026).

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S. and Kiela, D. (2020) ‘Retrieval-augmented generation for knowledge-intensive NLP tasks’, Advances in Neural Information Processing Systems, 33. Available at: https://papers.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html (Accessed: 9 September 2026).

Rao, A.S. and Georgeff, M.P. (1995) ‘BDI agents: from theory to practice’, in Proceedings of the First International Conference on Multiagent Systems, pp. 312–319. Available at: https://aaai.org/papers/icmas95-042-bdi-agents-from-theory-to-practice/ (Accessed: 9 September 2026).

Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K. and Yao, S. (2023) ‘Reflexion: language agents with verbal reinforcement learning’, Advances in Neural Information Processing Systems, 36. Available at: https://papers.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html (Accessed: 9 September 2026).

Wang, L., Ma, C., Feng, X., Zhang, Z., Yang, H., Zhang, J., Chen, Z., Tang, J., Chen, X., Lin, Y., Zhao, W.X., Wei, Z. and Wen, J. (2024) ‘A survey on large language model based autonomous agents’, Frontiers of Computer Science, 18(6), article 186345. Available at: https://doi.org/10.1007/s11704-024-40231-1 (Accessed: 9 September 2026).

Weidinger, L., Uesato, J., Rauh, M., Griffin, C., Huang, P.-S., Mellor, J., Glaese, A., Cheng, M., Balle, B., Kasirzadeh, A. et al. (2022) ‘Taxonomy of risks posed by language models’, in Proceedings of the 2022 ACM Conference on Fairness, Accountability, and Transparency, pp. 214–229. Available at: https://doi.org/10.1145/3531146.3533088 (Accessed: 9 September 2026).

Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K.R. and Cao, Y. (2023) ‘ReAct: synergizing reasoning and acting in language models’, International Conference on Learning Representations. Available at: https://mlanthology.org/iclr/2023/yao2023iclr-react/ (Accessed: 9 September 2026).

Zhao, W.X., Zhou, K., Li, J., Tang, T., Wang, X., Hou, Y., Min, Y., Zhang, B., Zhang, J., Dong, Z. et al. (2023) ‘A survey of large language models’, arXiv preprint arXiv:2303.18223. Available at: https://arxiv.org/abs/2303.18223 (Accessed: 9 September 2026).

---

## Final Status

The current prototype demonstrates the complete autonomous workflow:

    Research Question
            ↓
    Planner Agent
            ↓
    Academic Search Plan
            ↓
    Retrieval Agent
            ↓
    Validation / Deduplication / Ranking
            ↓
    Critic Agent
            ↓
    Replan if required
            ↓
    Reporter Agent
            ↓
    SQLite Persistence
            ↓
    Browser Research Report

The final automated test suite contains 26 passing tests across unit, integration, and functional test levels.