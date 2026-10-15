/**
 * Dataset loader.
 *
 * Locates and parses `dataset/dataset.json`. Supports two modes:
 *
 * 1. **Local mode** (default): reads `../dataset/dataset.json` relative to
 *    the compiled `dist/` directory. Used when the MCP server is run from
 *    a clone of this repo.
 *
 * 2. **Remote mode** (`LLM_RACE_DATASET_URL` set): fetches from the given
 *    HTTPS URL with a 1-hour in-memory cache. Used when the MCP server is
 *    distributed via npm and consumes the canonical dataset hosted on
 *    GitHub Pages or jsDelivr.
 *
 * Both paths resolve to the same `Dataset` interface, so all downstream
 * code is mode-agnostic.
 */

import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { Dataset, Model } from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Default location: ../dataset/dataset.json relative to compiled dist/ */
function defaultLocalPath(): string {
  // dist/ → ../dataset/dataset.json (one level up from package root)
  return resolve(__dirname, "..", "..", "dataset", "dataset.json");
}

interface CacheEntry {
  data: Dataset;
  loadedAt: number;
}

const CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour
let cache: CacheEntry | null = null;

async function loadFromFile(path: string): Promise<Dataset> {
  const raw = await readFile(path, "utf-8");
  return JSON.parse(raw) as Dataset;
}

async function loadFromUrl(url: string): Promise<Dataset> {
  const resp = await fetch(url, {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) {
    throw new Error(
      `Failed to fetch dataset from ${url}: HTTP ${resp.status} ${resp.statusText}`,
    );
  }
  return (await resp.json()) as Dataset;
}

/**
 * Get the current dataset, using the cache when fresh.
 * Throws on first-time load failure; subsequent failures return stale cache.
 */
export async function getDataset(): Promise<Dataset> {
  const now = Date.now();
  if (cache && now - cache.loadedAt < CACHE_TTL_MS) {
    return cache.data;
  }

  const url = process.env.LLM_RACE_DATASET_URL;
  const localPath = process.env.LLM_RACE_DATASET_PATH ?? defaultLocalPath();

  try {
    const data = url
      ? await loadFromUrl(url)
      : await loadFromFile(localPath);
    cache = { data, loadedAt: now };
    return data;
  } catch (err) {
    if (cache) {
      // Network blip / file lock — fall back to stale cache rather than failing
      console.error(
        `[llm-race] dataset reload failed, using stale cache:`,
        err instanceof Error ? err.message : err,
      );
      return cache.data;
    }
    throw err;
  }
}

/** Force-clear the cache (for tests or manual refresh). */
export function clearCache(): void {
  cache = null;
}

/** Convenience: get just the models array. */
export async function getModels(): Promise<Model[]> {
  const dataset = await getDataset();
  return dataset.models;
}

/** Find a single model by exact ID. */
export async function getModelById(id: string): Promise<Model | null> {
  const models = await getModels();
  return models.find((m) => m.id === id) ?? null;
}

/** Find models by case-insensitive substring match on id or name. */
export async function searchModels(query: string): Promise<Model[]> {
  const models = await getModels();
  const q = query.toLowerCase();
  return models.filter(
    (m) =>
      m.id.toLowerCase().includes(q) ||
      m.name.toLowerCase().includes(q) ||
      m.vendor.toLowerCase().includes(q),
  );
}
