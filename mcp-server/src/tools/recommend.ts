/**
 * MCP tool: recommend_for_pipeline_step
 *
 * The flagship tool. Takes a high-level scenario description plus optional
 * hard constraints / weights, and returns a ranked list of suitable models
 * with bilingual rationales.
 *
 * This Step 4 MVP version uses heuristic weight presets keyed off the
 * `scenario` parameter. Step 5 will extend with budget-aware optimization
 * and pipeline-aware composition (e.g. recommend a cheap + a strong model
 * for a 2-stage pipeline).
 */

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { getModels } from "../dataset.js";
import {
  applyHardConstraints,
  DEFAULT_WEIGHTS,
  rankModels,
  type HardConstraints,
  type ScoringWeights,
} from "../scoring.js";

const MODALITY_VALUES = ["text", "image", "audio", "video", "pdf"] as const;

const SCENARIO_VALUES = [
  "general",
  "coding",
  "long_context",
  "cheap_bulk",
  "cutting_edge",
  "low_hallucination",
  "multilingual_zh",
  "vision",
] as const;

const inputShape = {
  scenario: z
    .enum(SCENARIO_VALUES)
    .optional()
    .describe(
      "High-level use case preset. Adjusts default weights. Defaults to 'general'.",
    ),
  required_modalities_in: z
    .array(z.enum(MODALITY_VALUES))
    .optional()
    .describe("Hard constraint: required input modalities"),
  required_modalities_out: z
    .array(z.enum(MODALITY_VALUES))
    .optional()
    .describe("Hard constraint: required output modalities"),
  min_context_window: z.number().int().positive().optional(),
  max_input_price: z.number().positive().optional(),
  max_output_price: z.number().positive().optional(),
  vendors: z
    .array(z.string())
    .optional()
    .describe("Whitelist of vendors. Empty/undefined means all vendors allowed."),
  open_weight_only: z.boolean().optional(),
  top_k: z
    .number()
    .int()
    .positive()
    .max(20)
    .optional()
    .describe("Number of top models to return. Defaults to 5."),
  custom_weights: z
    .object({
      intelligence: z.number().optional(),
      price_input: z.number().optional(),
      price_output: z.number().optional(),
      context: z.number().optional(),
      speed: z.number().optional(),
      arena_elo: z.number().optional(),
      hallucination_inverse: z.number().optional(),
      recency: z.number().optional(),
    })
    .optional()
    .describe(
      "Override scoring weights. Any field omitted falls back to the scenario preset.",
    ),
};

type Scenario = (typeof SCENARIO_VALUES)[number];

type RecommendArgs = {
  scenario?: Scenario;
  required_modalities_in?: Array<(typeof MODALITY_VALUES)[number]>;
  required_modalities_out?: Array<(typeof MODALITY_VALUES)[number]>;
  min_context_window?: number;
  max_input_price?: number;
  max_output_price?: number;
  vendors?: string[];
  open_weight_only?: boolean;
  top_k?: number;
  custom_weights?: Partial<ScoringWeights>;
};

const SCENARIO_PRESETS: Record<Scenario, ScoringWeights> = {
  general: DEFAULT_WEIGHTS,
  coding: {
    intelligence: 1.5,
    price_input: 0.3,
    price_output: 0.5,
    context: 0.6,
    speed: 0.4,
    arena_elo: 0.5,
    hallucination_inverse: 0.4,
    recency: 0.4,
  },
  long_context: {
    intelligence: 0.8,
    price_input: 0.4,
    price_output: 0.6,
    context: 2.0,
    speed: 0.2,
    arena_elo: 0.3,
    hallucination_inverse: 0.6,
    recency: 0.3,
  },
  cheap_bulk: {
    intelligence: 0.4,
    price_input: 2.0,
    price_output: 2.0,
    context: 0.3,
    speed: 0.8,
    arena_elo: 0.2,
    hallucination_inverse: 0.3,
    recency: 0.1,
  },
  cutting_edge: {
    intelligence: 1.8,
    price_input: 0.1,
    price_output: 0.2,
    context: 0.6,
    speed: 0.2,
    arena_elo: 1.0,
    hallucination_inverse: 0.5,
    recency: 1.5,
  },
  low_hallucination: {
    intelligence: 0.8,
    price_input: 0.4,
    price_output: 0.5,
    context: 0.4,
    speed: 0.2,
    arena_elo: 0.6,
    hallucination_inverse: 2.5,
    recency: 0.3,
  },
  multilingual_zh: {
    intelligence: 1.2,
    price_input: 0.4,
    price_output: 0.5,
    context: 0.5,
    speed: 0.3,
    arena_elo: 0.7,
    hallucination_inverse: 0.5,
    recency: 0.4,
  },
  vision: {
    intelligence: 1.2,
    price_input: 0.3,
    price_output: 0.5,
    context: 0.5,
    speed: 0.3,
    arena_elo: 0.6,
    hallucination_inverse: 0.5,
    recency: 0.5,
  },
};

function mergeWeights(
  preset: ScoringWeights,
  overrides?: Partial<ScoringWeights>,
): ScoringWeights {
  if (!overrides) return preset;
  return {
    intelligence: overrides.intelligence ?? preset.intelligence,
    price_input: overrides.price_input ?? preset.price_input,
    price_output: overrides.price_output ?? preset.price_output,
    context: overrides.context ?? preset.context,
    speed: overrides.speed ?? preset.speed,
    arena_elo: overrides.arena_elo ?? preset.arena_elo,
    hallucination_inverse:
      overrides.hallucination_inverse ?? preset.hallucination_inverse,
    recency: overrides.recency ?? preset.recency,
  };
}

export function register(server: McpServer): void {
  server.tool(
    "recommend_for_pipeline_step",
    "Recommend the best LLM models for a given scenario, with optional hard constraints. Returns a ranked list with bilingual (zh/en) rationale.",
    inputShape,
    async (args: RecommendArgs) => {
      const scenario = args.scenario ?? "general";
      const preset = SCENARIO_PRESETS[scenario];
      const weights = mergeWeights(preset, args.custom_weights);

      const constraints: HardConstraints = {
        required_modalities_in: args.required_modalities_in,
        required_modalities_out: args.required_modalities_out,
        min_context_window: args.min_context_window,
        max_input_price: args.max_input_price,
        max_output_price: args.max_output_price,
        vendors: args.vendors,
        open_weight_only: args.open_weight_only,
      };

      const all = await getModels();
      const candidates = applyHardConstraints(all, constraints);

      const ranked = rankModels(candidates, weights, args.top_k ?? 5);

      const payload = {
        scenario,
        weights_used: weights,
        candidate_count: candidates.length,
        recommendations: ranked.map((r) => ({
          id: r.model.id,
          name: r.model.name,
          vendor: r.model.vendor,
          context_window: r.model.context_window,
          price: {
            input: r.model.price.input,
            output: r.model.price.output,
          },
          modalities_in: r.model.modalities_in,
          source_coverage: r.model.source_coverage,
          score: r.score,
          rationale_zh: r.rationale_zh,
          rationale_en: r.rationale_en,
        })),
        notes:
          candidates.length === 0
            ? "No models matched the hard constraints. Try relaxing them."
            : undefined,
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
