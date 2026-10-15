# LLM Race MCP server

TypeScript/Node.js 22+ server using MCP over stdio.

## Build and connect

Generate `dataset/dataset.json` using the [pipeline](../data-pipeline/) first.
From this directory:

```sh
npm ci
npm run typecheck
npm run build
npm test
```

Tests use synthetic data and need no credentials or generated dataset.

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

Replace the path with your checkout's absolute path. Windows JSON paths can use
forward slashes. No published npm package or hosted dataset is assumed.

## Tools

| Name | Behavior |
| --- | --- |
| `list_models` | Filter/sort summaries |
| `get_model` | Full record by exact ID, then substring search |
| `recommend_for_pipeline_step` | Scenario presets, constraints and custom weights |

`compare_models` is planned. `tools/list` exposes input schemas.
Recommendation rationales are bilingual; other responses are structured records.
Prices are USD per million tokens, not monthly budgets.

Example recommendation arguments:

```json
{"scenario":"long_context","min_context_window":128000,"top_k":3}
```

## Dataset configuration

- Default: `<repo>/dataset/dataset.json`, relative to the compiled server.
- `LLM_RACE_DATASET_PATH`: custom local path.
- `LLM_RACE_DATASET_URL`: remote JSON URL, taking precedence.

Use trusted sources and HTTPS for remote data. The one-hour in-memory cache
falls back to stale data after reload failures. Initial load failure stops
startup. Remote JSON has no runtime schema validation.
See [design limitations](../DESIGN.md).
