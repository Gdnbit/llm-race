/**
 * TypeScript types mirroring the Pydantic models in `data-pipeline/src/models.py`.
 *
 * The Pydantic definitions are the canonical serialization contract —
 * if the pipeline ever changes the shape, both this file and the Pydantic
 * model must be updated.
 */

export type Modality = "text" | "image" | "audio" | "video" | "pdf";

export type Tier = 1 | 2 | 3;

export interface Price {
  /** USD per 1M input tokens */
  input: number;
  /** USD per 1M output tokens */
  output: number;
  cache_read: number | null;
  cache_write: number | null;
  image_per_unit: number | null;
  request_flat: number | null;
}

export interface Speed {
  tokens_per_sec_median: number | null;
  ttft_ms_p50: number | null;
  source: string | null;
  last_updated: string | null;
}

export interface IntelligenceIndex {
  score: number | null;
  source: string;
  last_updated: string | null;
}

export interface BenchRef {
  name: string;
  raw_score: number;
  source_url: string;
  date: string;
}

export interface Benchmarks {
  coding: BenchRef[];
  reasoning: BenchRef[];
  knowledge: BenchRef[];
  instruction_following: BenchRef[];
  multilingual_zh: BenchRef[];
  multimodal_vision: BenchRef[];
  long_context: BenchRef[];
  tool_use: BenchRef[];
  safety: BenchRef[];
}

export interface HumanPreference {
  arena_elo: number | null;
  arena_rank: number | null;
  source: string;
  last_updated: string | null;
}

export interface HallucinationRate {
  score: number | null;
  source: string;
  last_updated: string | null;
}

export interface Meta {
  benchmark_saturated: string[];
  contamination_warning: string[];
  auto_flags: string[];
}

export interface DataFreshness {
  last_pipeline_run: string;
  has_stale_fields: boolean;
}

export interface Availability {
  openrouter: boolean;
  api_direct: boolean;
  regions: string[];
  rate_limit_notes: string | null;
}

export interface Model {
  id: string;
  name: string;
  vendor: string;
  family: string | null;
  version: string | null;
  release_date: string | null;
  is_open_weight: boolean;
  license: string | null;
  tier: Tier;
  source_coverage: string[];
  modalities_in: Modality[];
  modalities_out: Modality[];
  context_window: number;
  context_effective: number | null;
  price: Price;
  speed: Speed;
  intelligence_index: IntelligenceIndex;
  benchmarks: Benchmarks;
  human_preference: HumanPreference;
  hallucination_rate: HallucinationRate;
  usage_rank: number | null;
  availability: Availability;
  meta: Meta;
  data_freshness: DataFreshness;
}

export interface SourceMeta {
  name: string;
  last_fetched_at: string;
  model_count: number;
  status: "ok" | "partial" | "failed";
  error: string | null;
}

export interface Dataset {
  schema_version: string;
  generated_at: string;
  models: Model[];
  sources: SourceMeta[];
}

/**
 * A "skinny" model record — the subset of fields most useful for the AI agent
 * when listing many models, omitting empty arrays and verbose nesting.
 */
export interface ModelSummary {
  id: string;
  name: string;
  vendor: string;
  tier: Tier;
  context_window: number;
  modalities_in: Modality[];
  price: {
    input: number;
    output: number;
  };
  intelligence_score: number | null;
  arena_elo: number | null;
  source_coverage: string[];
  release_date: string | null;
}

export function toSummary(model: Model): ModelSummary {
  return {
    id: model.id,
    name: model.name,
    vendor: model.vendor,
    tier: model.tier,
    context_window: model.context_window,
    modalities_in: model.modalities_in,
    price: {
      input: model.price.input,
      output: model.price.output,
    },
    intelligence_score: model.intelligence_index.score,
    arena_elo: model.human_preference.arena_elo,
    source_coverage: model.source_coverage,
    release_date: model.release_date,
  };
}
