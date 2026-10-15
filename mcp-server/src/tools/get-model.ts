/**
 * MCP tool: get_model
 *
 * Returns the full record for a single model. If exact ID lookup fails,
 * falls back to substring search on id / name / vendor and returns
 * matching candidates so the agent can pick the right one.
 */

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { getModelById, searchModels } from "../dataset.js";
import { toSummary } from "../types.js";

const inputShape = {
  id: z
    .string()
    .describe(
      "Model ID (e.g. 'anthropic/claude-opus-4.7') or a free-text query " +
        "matched against id/name/vendor. Exact ID match takes precedence.",
    ),
};

type GetModelArgs = { id: string };

export function register(server: McpServer): void {
  server.tool(
    "get_model",
    "Get the full record for a single LLM model by its canonical ID. Falls back to fuzzy search if no exact match.",
    inputShape,
    async (args: GetModelArgs) => {
      const exact = await getModelById(args.id);
      if (exact) {
        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(exact, null, 2),
            },
          ],
        };
      }

      const fuzzy = await searchModels(args.id);
      if (fuzzy.length === 0) {
        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(
                {
                  error: "not_found",
                  query: args.id,
                  hint: "Try `list_models` to browse, or use a vendor prefix (e.g. 'anthropic/').",
                },
                null,
                2,
              ),
            },
          ],
          isError: true,
        };
      }

      if (fuzzy.length === 1) {
        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(fuzzy[0], null, 2),
            },
          ],
        };
      }

      // Multiple candidates — return summaries so the agent can disambiguate
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(
              {
                hint: "Multiple matches — call get_model again with a more specific id.",
                query: args.id,
                candidates: fuzzy.slice(0, 20).map(toSummary),
              },
              null,
              2,
            ),
          },
        ],
      };
    },
  );
}
