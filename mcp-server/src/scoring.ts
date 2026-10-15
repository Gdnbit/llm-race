/**
 * Scoring & ranking logic.
 *
 * This is the recommendation engine's heart. The same algorithm runs in:
 *  - `mcp-server/src/scoring.ts` (this file, for MCP tools)
 *  - `web/lib/scoring.ts`        (for the React UI; planned to be a copy of this)
 *
 * Design principles:
 *  - **Pure functions**: easy to unit-test, no side effects.
 *  - **Tolerant of missing data**: a model with `intelligence_index.score = null`
 *    contributes 0 to the intelligence dimension rather than crashing.
 *  - **Normalized to [0, 1]** before weighting, so weights are comparable.
 *  - **Bilingual rationale strings** generated at recommend time for UX.
 */

import type { Model, Modality, Tier } from "./types.js";

// ────────────────────────── Public types ──────────────────────────

/**
 * Weights for each scoring dimension. Default weights map to the
 * "balanced" preset (roughly equal for intelligence/price/context).
 *
 * Weights need not sum to 1 — they're normalized internally.
 */
export interface ScoringWeights {
  intelligence: number;
  price_input: number;
  price_output: number;
  context: number;
  speed: number;
  arena_elo: number;
  hallucination_inverse: number;
  recency: number;
}

export const DEFAULT_WEIGHTS: ScoringWeights = {
  intelligence: 1.0,
  price_input: 0.6,
  price_output: 0.8,
  context: 0.4,
  speed: 0.3,
  arena_elo: 0.5,
  hallucination_inverse: 0.5,
  recency: 0.2,
};

export interface HardConstraints {
  /** Required input modalities (e.g. ["text", "image"]). All must be supported. */
  required_modalities_in?: Modality[];
  /** Required output modalities. */
  required_modalities_out?: Modality[];
  /** Minimum context window (tokens). */
  min_context_window?: number;
  /** Maximum input price USD/1M tokens. */
  max_input_price?: number;
  /** Maximum output price USD/1M tokens. */
  max_output_price?: number;
  /** Whitelist of vendors. */
  vendors?: string[];
  /** Only include models reachable via OpenRouter. */
  openrouter_only?: boolean;
  /** Only models in tier ≤ this value. */
  max_tier?: Tier;
  /** Only open-weight models. */
  open_weight_only?: boolean;
}

export interface ScoreBreakdown {
  intelligence: number;
  price_input: number;
  price_output: number;
  context: number;
  speed: number;
  arena_elo: number;
  hallucination_inverse: number;
  recency: number;
  total: number;
}

export interface ScoredModel {
  model: Model;
  score: ScoreBreakdown;
  rationale_zh: string;
  rationale_en: string;
}

// ────────────────────────── Hard filtering ──────────────────────────

export function applyHardConstraints(
  models: Model[],
  constraints: HardConstraints,
): Model[] {
  return models.filter((m) => satisfiesAll(m, constraints));
}

function satisfiesAll(m: Model, c: HardConstraints): boolean {
  if (c.required_modalities_in?.length) {
    if (!c.required_modalities_in.every((mod) => m.modalities_in.includes(mod))) {
      return false;
    }
  }
  if (c.required_modalities_out?.length) {
    if (!c.required_modalities_out.every((mod) => m.modalities_out.includes(mod))) {
      return false;
    }
  }
  if (c.min_context_window !== undefined && m.context_window < c.min_context_window) {
    return false;
  }
  if (c.max_input_price !== undefined && m.price.input > c.max_input_price) {
    return false;
  }
  if (c.max_output_price !== undefined && m.price.output > c.max_output_price) {
    return false;
  }
  if (c.vendors?.length && !c.vendors.includes(m.vendor)) {
    return false;
  }
  if (c.openrouter_only && !m.availability.openrouter) {
    return false;
  }
  if (c.max_tier !== undefined && m.tier > c.max_tier) {
    return false;
  }
  if (c.open_weight_only && !m.is_open_weight) {
    return false;
  }
  return true;
}

// ────────────────────────── Normalization ──────────────────────────

interface NormalizationStats {
  intelligence_max: number;
  price_input_min: number;
  price_input_max: number;
  price_output_min: number;
  price_output_max: number;
  context_max: number;
  speed_max: number;
  arena_elo_max: number;
  hallucination_max: number;
  newest_release_ts: number;
  oldest_release_ts: number;
}

function computeStats(models: Model[]): NormalizationStats {
  const intel = models.map((m) => m.intelligence_index.score ?? 0);
  const priceIn = models.map((m) => m.price.input);
  const priceOut = models.map((m) => m.price.output);
  const ctx = models.map((m) => m.context_window);
  const speed = models.map((m) => m.speed.tokens_per_sec_median ?? 0);
  const elo = models.map((m) => m.human_preference.arena_elo ?? 0);
  const hallu = models.map((m) => m.hallucination_rate.score ?? 0);
  const releases = models
    .map((m) => (m.release_date ? Date.parse(m.release_date) : NaN))
    .filter((t) => Number.isFinite(t));

  return {
    intelligence_max: Math.max(...intel, 1),
    price_input_min: Math.min(...priceIn.filter((p) => p > 0), Number.MAX_VALUE),
    price_input_max: Math.max(...priceIn, 1),
    price_output_min: Math.min(...priceOut.filter((p) => p > 0), Number.MAX_VALUE),
    price_output_max: Math.max(...priceOut, 1),
    context_max: Math.max(...ctx, 1),
    speed_max: Math.max(...speed, 1),
    arena_elo_max: Math.max(...elo, 1),
    hallucination_max: Math.max(...hallu, 0.01),
    newest_release_ts: releases.length ? Math.max(...releases) : Date.now(),
    oldest_release_ts: releases.length ? Math.min(...releases) : Date.now(),
  };
}

// Simple log-scale normalization for context window (since it spans 4-5 orders of magnitude)
function logNormalize(value: number, maxValue: number): number {
  if (value <= 0 || maxValue <= 0) return 0;
  return Math.log10(value + 1) / Math.log10(maxValue + 1);
}

// Inverse normalization — lower is better (price, hallucination)
function inverseNormalize(value: number, minValue: number, maxValue: number): number {
  if (value <= 0 || maxValue <= minValue) return 0;
  return 1 - (value - minValue) / (maxValue - minValue);
}

// ────────────────────────── Scoring ──────────────────────────

export function scoreModel(
  model: Model,
  weights: ScoringWeights,
  stats: NormalizationStats,
): ScoreBreakdown {
  // Each component is in [0, 1]; multiply by weight; sum.
  const intelligence =
    (model.intelligence_index.score ?? 0) / stats.intelligence_max;

  const price_input = inverseNormalize(
    model.price.input,
    stats.price_input_min,
    stats.price_input_max,
  );

  const price_output = inverseNormalize(
    model.price.output,
    stats.price_output_min,
    stats.price_output_max,
  );

  const context = logNormalize(model.context_window, stats.context_max);

  const speed =
    (model.speed.tokens_per_sec_median ?? 0) / stats.speed_max;

  const arena_elo =
    (model.human_preference.arena_elo ?? 0) / stats.arena_elo_max;

  const hallucination_inverse = inverseNormalize(
    model.hallucination_rate.score ?? stats.hallucination_max,
    0,
    stats.hallucination_max,
  );

  const releaseTs = model.release_date ? Date.parse(model.release_date) : NaN;
  const recency = Number.isFinite(releaseTs)
    ? (releaseTs - stats.oldest_release_ts) /
      Math.max(1, stats.newest_release_ts - stats.oldest_release_ts)
    : 0;

  // Weighted sum. Weights are normalized so total stays in [0, 1].
  const totalWeight = Object.values(weights).reduce((s, w) => s + Math.abs(w), 0) || 1;

  const total =
    (intelligence * weights.intelligence +
      price_input * weights.price_input +
      price_output * weights.price_output +
      context * weights.context +
      speed * weights.speed +
      arena_elo * weights.arena_elo +
      hallucination_inverse * weights.hallucination_inverse +
      recency * weights.recency) /
    totalWeight;

  return {
    intelligence: round(intelligence),
    price_input: round(price_input),
    price_output: round(price_output),
    context: round(context),
    speed: round(speed),
    arena_elo: round(arena_elo),
    hallucination_inverse: round(hallucination_inverse),
    recency: round(recency),
    total: round(total),
  };
}

function round(n: number, digits = 4): number {
  return Math.round(n * 10 ** digits) / 10 ** digits;
}

// ────────────────────────── Rationale generation ──────────────────────────

function dominantDimensions(
  breakdown: ScoreBreakdown,
  weights: ScoringWeights,
  topK = 3,
): Array<{ name: string; weighted: number }> {
  const items: Array<{ name: keyof ScoringWeights; weighted: number }> = [
    { name: "intelligence", weighted: breakdown.intelligence * weights.intelligence },
    { name: "price_input", weighted: breakdown.price_input * weights.price_input },
    { name: "price_output", weighted: breakdown.price_output * weights.price_output },
    { name: "context", weighted: breakdown.context * weights.context },
    { name: "speed", weighted: breakdown.speed * weights.speed },
    { name: "arena_elo", weighted: breakdown.arena_elo * weights.arena_elo },
    {
      name: "hallucination_inverse",
      weighted: breakdown.hallucination_inverse * weights.hallucination_inverse,
    },
    { name: "recency", weighted: breakdown.recency * weights.recency },
  ];
  return items
    .filter((i) => i.weighted > 0.001)
    .sort((a, b) => b.weighted - a.weighted)
    .slice(0, topK);
}

const DIMENSION_LABELS_ZH: Record<keyof ScoringWeights, string> = {
  intelligence: "综合智能",
  price_input: "输入价格",
  price_output: "输出价格",
  context: "上下文长度",
  speed: "推理速度",
  arena_elo: "人类偏好",
  hallucination_inverse: "幻觉率（低）",
  recency: "新鲜度",
};

const DIMENSION_LABELS_EN: Record<keyof ScoringWeights, string> = {
  intelligence: "intelligence",
  price_input: "input price",
  price_output: "output price",
  context: "context window",
  speed: "throughput",
  arena_elo: "human preference",
  hallucination_inverse: "low hallucination",
  recency: "recency",
};

export function generateRationale(
  model: Model,
  breakdown: ScoreBreakdown,
  weights: ScoringWeights,
): { zh: string; en: string } {
  const dims = dominantDimensions(breakdown, weights);
  const dimsZh = dims.map((d) => DIMENSION_LABELS_ZH[d.name as keyof ScoringWeights]);
  const dimsEn = dims.map((d) => DIMENSION_LABELS_EN[d.name as keyof ScoringWeights]);

  const priceStr = `$${model.price.input.toFixed(2)}/$${model.price.output.toFixed(2)} per 1M`;
  const ctxStr =
    model.context_window >= 1_000_000
      ? `${(model.context_window / 1_000_000).toFixed(1)}M`
      : `${(model.context_window / 1000).toFixed(0)}K`;

  const zh =
    dims.length > 0
      ? `主要优势：${dimsZh.join(" / ")}。价格 ${priceStr}，上下文 ${ctxStr}。`
      : `${model.name}：价格 ${priceStr}，上下文 ${ctxStr}。`;

  const en =
    dims.length > 0
      ? `Strengths: ${dimsEn.join(" / ")}. Pricing ${priceStr}, context ${ctxStr}.`
      : `${model.name}: pricing ${priceStr}, context ${ctxStr}.`;

  return { zh, en };
}

// ────────────────────────── Top-level recommend ──────────────────────────

export function rankModels(
  candidates: Model[],
  weights: ScoringWeights = DEFAULT_WEIGHTS,
  topK = 5,
): ScoredModel[] {
  if (candidates.length === 0) return [];

  const stats = computeStats(candidates);

  const scored = candidates.map((model) => {
    const breakdown = scoreModel(model, weights, stats);
    const rationale = generateRationale(model, breakdown, weights);
    return {
      model,
      score: breakdown,
      rationale_zh: rationale.zh,
      rationale_en: rationale.en,
    };
  });

  scored.sort((a, b) => b.score.total - a.score.total);
  return scored.slice(0, topK);
}
