# LLM Race design and implementation status

This document describes checked-in code. Roadmap items are labeled explicitly.
LLM Race helps agents shortlist models for a workflow step.

## 1. Boundaries

The pipeline collects metadata; the MCP server filters and ranks it. The server
does not call model inference. Consumers must evaluate candidates on their own
workloads. There is no account system or production availability guarantee.

## 2. Implemented architecture

1. `data-pipeline/src/build.py` runs an OpenRouter anchor phase, a LMArena
   enrichment phase, then merging and serialization.
2. OpenRouter supplies canonical `vendor/model` IDs, USD per million token
   prices, context windows, and modalities.
3. LMArena uses releases from `fboulnois/llm-leaderboard-csv`, a community feed.
   Release timestamps are retained; this source can lag the upstream leaderboard.
4. `alignment/` applies aliases, vendor-normalized exact matches, then fuzzy
   matching. Unmatched records are logged. No AI alignment call exists.
5. `merger.py` applies partial signals and tracks coverage. It mutates the
   supplied model records for that run.
6. Generated `dataset/dataset.json` is ignored by Git. There is no hosted
   canonical dataset or scheduled collection/publishing workflow.
7. The TypeScript server exposes three tools over stdio.

Adapters capture fetch failures in source metadata, allowing other sources to
contribute. Successful process exit does not guarantee usable data: inspect
source statuses and require nonempty anchor results.

## 3. Data contract

`data-pipeline/src/models.py` defines the Pydantic serialization contract.
`mcp-server/src/types.ts` mirrors it; both must change together.
Top-level fields are `schema_version`, `generated_at`, `models`, and `sources`.
Sources carry timestamps, model counts, status, and optional errors.

Records include identity, modalities, context, pricing, optional evaluation and
speed signals, availability, source coverage, and freshness metadata. Reserved
fields do not imply that data is collected. Intelligence, speed, benchmark and
hallucination values mostly remain null/empty. Automated staleness,
contamination and saturation detection are planned. Open-weight/license
metadata is not yet reliably enriched.

## 4. MCP behavior

### 4.1 Tools

| Tool | Behavior |
| --- | --- |
| `list_models` | Filter by vendor, modalities, context, price or open-weight flag; sort summaries |
| `get_model` | Exact ID, then case-insensitive substring search; multiple hits return candidates |
| `recommend_for_pipeline_step` | Hard constraints, scenario presets/custom weights, ranked summaries and bilingual rationales |

Input schemas in `src/tools/` are authoritative. Scenarios: `general`, `coding`,
`long_context`, `cheap_bulk`, `cutting_edge`, `low_hallucination`,
`multilingual_zh`, `vision`. Default result count is five. These names tune
heuristics; they do not imply dedicated task benchmarks.

### 4.2 Coverage tiers and scoring

`merger.py` assigns tier 1 for at least four sources, tier 2 for two or three,
and tier 3 for one. With two implemented adapters, tier 1 is not reached.

Scoring uses normalized intelligence, input/output price, context, speed,
Arena Elo, inverse hallucination, and recency. Missing signals contribute little
or nothing. Weights are normalized within the candidate set; scores are relative
heuristics, not calibrated performance probabilities. Zero/unknown prices and
missing metrics require care when changing policy.

## 5. Configuration and caching

The pipeline reads process variables and optionally `data-pipeline/.env`.
The simple loader supports unquoted `KEY=value`, not shell expansion.
Empty `DATASET_OUTPUT_PATH` uses `<repo>/dataset/dataset.json`.
`PIPELINE_MODE` is a logged label; `quick` currently does not skip adapters.
Artificial Analysis, Anthropic and Hugging Face keys are reserved and unused.

MCP reads the local dataset by default. `LLM_RACE_DATASET_PATH` overrides its
path; `LLM_RACE_DATASET_URL` takes precedence. Use a trusted HTTPS URL without
embedded credentials. Cache TTL is one hour in memory. Reload errors return
stale cached data when available; initial load errors fail startup.
Remote JSON is trusted via a TypeScript cast, without runtime validation or
persistent disk caching.

## 6. Planned work and acceptance criteria

| Work | Acceptance criteria |
| --- | --- |
| Artificial Analysis | Document terms/access; map intelligence/speed with timestamps and failure fixtures |
| Hugging Face metadata | Map IDs to weight/license metadata with provenance and unresolved-ID reporting |
| Vectara, SWE-Bench, LiveCodeBench | Separate adapters with source terms, units, coverage and fixtures |
| `compare_models` | Existing dataset only; explicit missing values, dimensions, provenance and MCP tests |
| Alignment | Regression fixtures for aliases, ambiguous versions and false positives |
| Data quality | Nonempty anchors, meaningful exit status, stale-source reporting, runtime schema validation |
| Web UI | Standalone accessible comparison using the dataset contract |
| Scheduled collection | Quality gates, minimal credentials, source-term review and validated artifacts |
| Monitoring / AI alignment | Define privacy, cost, confidence and change-history policies first |

Offline CI runs baseline pipeline unit tests and an MCP protocol smoke test.
Broader HTTP, retry, schema-compatibility and scoring coverage remain planned.
