#!/usr/bin/env node
/**
 * LLM_Race MCP server — entry point.
 *
 * Speaks Model Context Protocol over stdio. Run via:
 *   node dist/index.js
 *
 * Example MCP configuration:
 *
 *   {
 *     "mcpServers": {
 *       "llm-race": {
 *         "command": "node",
 *         "args": ["/absolute/path/to/LLM_Race/mcp-server/dist/index.js"]
 *       }
 *     }
 *   }
 *
 * Environment variables (all optional):
 *   LLM_RACE_DATASET_URL   — Remote dataset.json URL (default: local file)
 *   LLM_RACE_DATASET_PATH  — Custom local file path
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { getDataset } from "./dataset.js";
import * as listModels from "./tools/list-models.js";
import * as getModel from "./tools/get-model.js";
import * as recommend from "./tools/recommend.js";

const PACKAGE_NAME = "llm-race";
const PACKAGE_VERSION = "0.1.0";

async function main(): Promise<void> {
  try {
    const dataset = await getDataset();
    console.error(
      `[llm-race] loaded dataset: ${dataset.models.length} models, ` +
        `generated ${dataset.generated_at}`,
    );
  } catch (err) {
    console.error(
      `[llm-race] FATAL: failed to load dataset:`,
      err instanceof Error ? err.message : err,
    );
    console.error(
      `[llm-race] Hint: set LLM_RACE_DATASET_URL or run "uv run python -m src.build" in data-pipeline/ first.`,
    );
    process.exit(1);
  }

  const server = new McpServer({
    name: PACKAGE_NAME,
    version: PACKAGE_VERSION,
  });

  listModels.register(server);
  getModel.register(server);
  recommend.register(server);

  const transport = new StdioServerTransport();
  await server.connect(transport);

  console.error(`[llm-race] MCP server ready (stdio)`);
}

main().catch((err) => {
  console.error(`[llm-race] FATAL:`, err);
  process.exit(1);
});
