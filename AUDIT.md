# Investigation audit and progress

The existing Planner → Retrieval → Processing → Critic → Reporter graph and its
bounded replanning route are unchanged. Each graph node is wrapped with an
observer that commits its start, completion or failure to SQLite. The provider
adapters and language-model interfaces retain their existing responsibilities.

`investigation_runs` stores a UUID run identifier, eventual report identifier,
UTC timestamps, status, current stage and metric snapshot. `investigation_events`
stores ordered events with run identifier, timestamp, component, action and JSON
details. Events resolve their report identifier through the parent run, including
events created before a report exists. Existing report rows are preserved; the
new tables are created automatically on first audit access.

Metrics have these definitions:

| Metric | Meaning |
| --- | --- |
| Elapsed seconds | Wall-clock duration across graph stages, including provider and model calls, measured with a monotonic clock; excludes the browser and queue wait |
| Search cycles | Completed planning cycles |
| Queries generated | Total queries in completed plans, including repeated queries |
| Raw papers retrieved | All normalised Paper records returned by provider adapters across cycles, before processing; not raw HTTP items rejected inside an adapter |
| Valid papers retained | Records surviving validation, before deduplication |
| Noisy records removed | Invalid titles and excluded publication fragments |
| Duplicates removed | Valid records removed by existing DOI/title deduplication |
| Relevant papers retained | Unique papers passing relevance filtering, before the evidence limit |
| Irrelevant records removed | Unique valid papers below the relevance threshold |
| Evidence limit removed | Relevant papers outside the top-ten evidence set |
| Provider failures | Failed provider calls; one failure per provider/query attempt |
| Final evidence count | Latest processed evidence count, confirmed from report sources on completion |

Processing revisits the accumulated corpus on each cycle. Its metrics replace
the preceding snapshot instead of accumulating, avoiding double counting.
Per-cycle counts and stage durations remain available in the worklog. Failed
runs preserve metrics from completed stages and elapsed time to the failure.

Critic events contain its structured sufficiency decision and a brief public
evidence assessment, the actual next stage and whether the search cycle limit
prevented further retrieval. The Critic prompt requests a concise public reason.
Reasoning tags are removed defensively. Prompts, raw model responses, private
reasoning fields and exception messages are never written to the audit.

With JavaScript, the form submits to `POST /runs` and polls
`GET /runs/<run_id>/status`. Status responses contain only an allowlisted stage
message, status and identifiers/links. They do not contain Critic reasons or
audit details. Fast stages may finish between polls. There are no simulated
stage transitions. A tab-local saved URL resumes polling after refresh;
temporary connection failures retry the same run.

Completed reports can be revisited at `GET /runs/<run_id>/report`, with a separate
Investigation and audit tab. Tabs support keyboard navigation and escaped
content. Without JavaScript the original synchronous form still works and both
report sections remain readable.

This remains a local Flask prototype. At most two asynchronous investigations
run per application instance. Workers run in the Flask process: stopping that
process interrupts active work, which is not automatically resumed. Its committed
events remain in SQLite, but a running status can remain stale after an abrupt
shutdown. Start a fresh investigation after restarting. A production deployment
would require a durable worker queue and run ownership/access controls.

## Verification

Run the Python suite from the project root:

```text
python -m pytest -q
```

Run the browser-script behaviour tests with Node.js (no added packages):

```text
node --test tests/javascript/progress.test.cjs
```

Tests use isolated temporary SQLite databases and mocked model/provider calls.
They do not send live research requests or change the application's saved reports.
