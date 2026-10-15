#!/usr/bin/env node
/** Offline MCP protocol check using synthetic data, never live model metadata. */
import assert from "node:assert/strict";
import { mkdtemp, writeFile, unlink, rmdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const date = "2026-01-01T00:00:00Z";
function model(id, inputPrice, context, modalities) {
  return {
    id, name: id.split("/")[1], vendor: "example",
    family: null, version: null, release_date: "2026-01-01",
    is_open_weight: false, license: null, tier: 3,
    source_coverage: ["synthetic"], modalities_in: modalities,
    modalities_out: ["text"], context_window: context, context_effective: null,
    price: { input: inputPrice, output: inputPrice * 2,
      cache_read: null, cache_write: null, image_per_unit: null, request_flat: null },
    speed: { tokens_per_sec_median: null, ttft_ms_p50: null, source: null, last_updated: null },
    intelligence_index: { score: null, source: "synthetic", last_updated: null },
    benchmarks: Object.fromEntries(["coding", "reasoning", "knowledge",
      "instruction_following", "multilingual_zh", "multimodal_vision",
      "long_context", "tool_use", "safety"].map((k) => [k, []])),
    human_preference: { arena_elo: null, arena_rank: null, source: "synthetic", last_updated: null },
    hallucination_rate: { score: null, source: "synthetic", last_updated: null },
    usage_rank: null,
    availability: { openrouter: false, api_direct: false, regions: [], rate_limit_notes: null },
    meta: { benchmark_saturated: [], contamination_warning: [], auto_flags: [] },
    data_freshness: { last_pipeline_run: date, has_stale_fields: false },
  };
}

async function main() {
  const dir = await mkdtemp(join(tmpdir(), "llm-race-smoke-"));
  const path = join(dir, "dataset.json");
  const client = new Client({ name: "llm-race-smoke", version: "1.0.0" }, { capabilities: {} });
  try {
    await writeFile(path, JSON.stringify({
      schema_version: "0.1.0", generated_at: date, sources: [],
      models: [
        model("example/compact", 0.1, 16000, ["text"]),
        model("example/vision", 2, 128000, ["text", "image"]),
      ],
    }));
    await client.connect(new StdioClientTransport({
      command: process.execPath,
      args: [fileURLToPath(new URL("../dist/index.js", import.meta.url))],
      env: { LLM_RACE_DATASET_PATH: path, LLM_RACE_DATASET_URL: "" },
    }));
    const tools = await client.listTools();
    assert.deepEqual(tools.tools.map((t) => t.name).sort(),
      ["get_model", "list_models", "recommend_for_pipeline_step"]);
    async function call(name, args) {
      const result = await client.callTool({ name, arguments: args });
      assert.ok(!result.isError, "Unexpected MCP error");
      return JSON.parse(result.content[0].text);
    }
    const listed = await call("list_models", { vendor: "example", sort_by: "price_input" });
    assert.equal(listed.total_matched, 2);
    assert.equal(listed.models[0].id, "example/compact");
    const filtered = await call("list_models", { required_modalities_in: ["image"] });
    assert.deepEqual(filtered.models.map((m) => m.id), ["example/vision"]);
    assert.equal((await call("get_model", { id: "example/compact" })).id, "example/compact");
    assert.equal((await call("get_model", { id: "vision" })).id, "example/vision");
    const missing = await client.callTool({ name: "get_model", arguments: { id: "absent" } });
    assert.equal(missing.isError, true);
    const rec = await call("recommend_for_pipeline_step",
      { scenario: "cheap_bulk", max_input_price: 1, top_k: 3 });
    assert.deepEqual(rec.recommendations.map((r) => r.id), ["example/compact"]);
    assert.ok(Number.isFinite(rec.recommendations[0].score.total));
    assert.ok(rec.recommendations[0].rationale_zh);
    assert.ok(rec.recommendations[0].rationale_en);
    const vision = await call("recommend_for_pipeline_step",
      { scenario: "long_context", required_modalities_in: ["image"], top_k: 3 });
    assert.deepEqual(vision.recommendations.map((r) => r.id), ["example/vision"]);
    console.log("MCP smoke test passed: discovery, filters, lookup, errors, recommendations.");
  } finally {
    await client.close();
    await unlink(path).catch(() => {});
    await rmdir(dir);
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
