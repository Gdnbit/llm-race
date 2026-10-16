# LLM Race by Gdnbit

**LLM Race — an MCP-powered model selection engine for AI agents.**

Built and maintained by [Gdnbit](https://github.com/Gdnbit).

Shortlist language models for a workflow step using prices, context, modalities,
and available evaluation signals. Agents receive ranked candidates, score
breakdowns, and Chinese/English rationales through MCP. Validate the shortlist
against your own workload before selecting a model.

## Current status

Early MVP. Missing metrics and source freshness affect recommendation quality.

| Component | Status |
| --- | --- |
| OpenRouter adapter | Implemented: catalog IDs, prices, context, modalities |
| LMArena adapter | Implemented via a community CSV feed; coverage/freshness vary |
| Model alignment | Implemented: aliases, vendor normalization, exact/fuzzy matching |
| MCP | Three tools: `list_models`, `get_model`, `recommend_for_pipeline_step` |
| Recommendations | Partial: heuristic presets/custom weights; benchmark, speed and hallucination fields mostly empty |
| Artificial Analysis, Hugging Face, Vectara, SWE-Bench, LiveCodeBench | Planned adapters |
| `compare_models`, change monitoring, AI-assisted alignment | Planned |
| Web UI and hosted dataset | Planned; `web/` contains documentation only |
| CI | Offline pipeline checks and MCP smoke test; no scheduled data publishing |

## Architecture

```text
OpenRouter catalog ──> canonical model records
LMArena CSV ────────> alias / exact / fuzzy alignment
                                  │
                             merge + tiers
                                  │
                        dataset/dataset.json
                                  │
                      TypeScript MCP server (stdio)
                                  │
                             AI agent client
```

- [data-pipeline/](data-pipeline/): Python ingestion and Pydantic schema.
- [mcp-server/](mcp-server/): TypeScript tools and scoring.
- [DESIGN.md](DESIGN.md): implementation contracts, limitations, and roadmap.

## Quick start

Requires Git, Python 3.11+, uv, and Node.js 22+ with npm.

```sh
git clone https://github.com/Gdnbit/llm-race.git
cd llm-race/data-pipeline
uv sync --locked
uv run python -m src.build --pretty
cd ../mcp-server
npm ci
npm run build
```

The pipeline requires internet access. Both implemented sources can be queried
without credentials; upstream availability and rate limits apply. Generated
`dataset/dataset.json` is excluded from Git. Review `sources[].status` and model
count: the current CLI can exit successfully with failed sources or empty data.

For optional credentials, copy `data-pipeline/.env.example` to
`data-pipeline/.env`. Shell variables take precedence. Never commit `.env`.
Reserved keys do not enable unimplemented adapters.

## Connect MCP

After building the dataset and server, add this to your MCP client configuration.
Replace the example path with your clone's absolute path.

```json
{
  "mcpServers": {
    "llm-race": {
      "command": "node",
      "args": ["/path/to/llm-race/mcp-server/dist/index.js"]
    }
  }
}
```

Reconnect your client and ask the agent to call `recommend_for_pipeline_step`
with `scenario: "long_context"`, `min_context_window: 128000`, and `top_k: 3`.
See [MCP setup](mcp-server/README.md) for dataset overrides. No npm registry
publication or hosted service is assumed.

## Pipeline and development checks

```sh
cd data-pipeline
uv run python -m src.build --dry-run
uv run python -m unittest discover -s tests -v
cd ../mcp-server
npm run typecheck
npm run build
npm test
```

Tests use synthetic inputs and no API credentials. The pipeline command is a
separate live check; `--dry-run` fetches data without saving it.

## Roadmap

- Add Artificial Analysis and Hugging Face metadata adapters.
- Improve cross-source alignment and missing/stale-data reporting.
- Add `compare_models` and deeper pipeline/scoring regression coverage.
- Build a standalone web comparison UI using the same dataset contract.
- Add scheduled collection after source terms and quality gates are defined.

## About the maintainer

**Gdnbit** is an AI Solution & Product Engineer focused on enterprise AI delivery,
agent systems, workflow automation and AI-native development.

- Profile: https://github.com/Gdnbit
- AI-readable candidate skill: https://github.com/Gdnbit/Gdnbit/tree/main/skills/gdnbit-candidate

The candidate skill is intentionally evidence-aware: it separates public proof,
private/building work and planning instead of treating every project description
as equally verified.

## Contributing and license

Use one `feature/<name>` branch and one PR per change. Read
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

MIT © 2026 Gdnbit. See [LICENSE](LICENSE). MIT covers project code; third-party
data and model licenses remain governed by their respective sources.
