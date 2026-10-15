/**
 * MCP tool: list_models
 *
 * Returns a filterable list of models (in summary form) with optional sorting.
 * Used by AI agents to discover what's available before drilling into details.
 */

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { getModels } from "../dataset.js";
import { type ModelSummary, toSummary } from "../types.js";

const MODALITY_VALUES = ["text", "image", "audio", "video", "pdf"] as const;
const SORT_FIELDS = [
  "price_input",
  "price_output",
  "context_window",
  "intelligence_score",
  "arena_elo",
  "release_date",
] as const;

const inputShape = {
  vendor: z
    .string()
    .optional()
    .describe("Filter by vendor (e.g. 'anthropic', 'openai', 'google')"),
  required_modalities_in: z
    .array(z.enum(MODALITY_VALUES))
    .optional()
    .describe("Required input modalities — all must be supported"),
  required_modalities_out: z
    .array(z.enum(MODALITY_VALUES))
    .optional()
    .describe("Required output modalities — all must be supported"),
  min_context_window: z
    .number()
    .int()
    .positive()
    .optional()
    .describe("Minimum context window in tokens"),
  max_input_price: z
    .number()
    .positive()
    .optional()
    .describe("Max input price (USD per 1M tokens)"),
  max_output_price: z
    .number()
    .positive()
    .optional()
    .describe("Max output price (USD per 1M tokens)"),
  open_weight_only: z
    .boolean()
    .optional()
    .describe("Only include open-weight models"),
  sort_by: z
    .enum(SORT_FIELDS)
    .optional()
    .describe("Sort field. Defaults to no sort (insertion order)."),
  sort_order: z
    .enum(["asc", "desc"])
    .optional()
    .describe("Sort direction. Defaults to 'asc' for price, 'desc' for the rest."),
  limit: z
    .number()
    .int()
    .positive()
    .max(200)
    .optional()
    .describe("Max number of results. Defaults to 50."),
};

type ListModelsArgs = {
  vendor?: string;
  required_modalities_in?: Array<typeof MODALITY_VALUES[number]>;
  required_modalities_out?: Array<typeof MODALITY_VALUES[number]>;
  min_context_window?: number;
  max_input_price?: number;
  max_output_price?: number;
  open_weight_only?: boolean;
  sort_by?: typeof SORT_FIELDS[number];
  sort_order?: "asc" | "desc";
  limit?: number;
};

function defaultSortOrder(sortBy: typeof SORT_FIELDS[number]): "asc" | "desc" {
  return sortBy === "price_input" || sortBy === "price_output" ? "asc" : "desc";
}

function compareSummaries(
  a: ModelSummary,
  b: ModelSummary,
  field: typeof SORT_FIELDS[number],
): number {
  switch (field) {
    case "price_input":
      return a.price.input - b.price.input;
    case "price_output":
      return a.price.output - b.price.output;
    case "context_window":
      return a.context_window - b.context_window;
    case "intelligence_score":
      return (a.intelligence_score ?? -1) - (b.intelligence_score ?? -1);
    case "arena_elo":
      return (a.arena_elo ?? -1) - (b.arena_elo ?? -1);
    case "release_date": {
      const aTs = a.release_date ? Date.parse(a.release_date) : 0;
      const bTs = b.release_date ? Date.parse(b.release_date) : 0;
      return aTs - bTs;
    }
  }
}

export function register(server: McpServer): void {
  server.tool(
    "list_models",
    "List LLM models with optional filters and sorting. Returns a compact summary array suitable for browsing. Use `get_model` for full details.",
    inputShape,
    async (args: ListModelsArgs) => {
      const models = await getModels();

      const filtered = models.filter((m) => {
        if (args.vendor && m.vendor.toLowerCase() !== args.vendor.toLowerCase()) {
          return false;
        }
        if (args.required_modalities_in?.length) {
          if (!args.required_modalities_in.every((mod) => m.modalities_in.includes(mod))) {
            return false;
          }
        }
        if (args.required_modalities_out?.length) {
          if (!args.required_modalities_out.every((mod) => m.modalities_out.includes(mod))) {
            return false;
          }
        }
        if (args.min_context_window !== undefined && m.context_window < args.min_context_window) {
          return false;
        }
        if (args.max_input_price !== undefined && m.price.input > args.max_input_price) {
          return false;
        }
        if (args.max_output_price !== undefined && m.price.output > args.max_output_price) {
          return false;
        }
        if (args.open_weight_only && !m.is_open_weight) {
          return false;
        }
        return true;
      });

      const summaries = filtered.map(toSummary);

      if (args.sort_by) {
        const order = args.sort_order ?? defaultSortOrder(args.sort_by);
        const direction = order === "asc" ? 1 : -1;
        summaries.sort((a, b) => direction * compareSummaries(a, b, args.sort_by!));
      }

      const limit = args.limit ?? 50;
      const limited = summaries.slice(0, limit);

      const payload = {
        total_matched: filtered.length,
        returned: limited.length,
        models: limited,
      };

      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(payload, null, 2),
          },
        ],
      };
    },
  );
}
