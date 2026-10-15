"""Offline release checks; all inputs are synthetic and contain no credentials."""

import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.build import _setup_logging, run_pipeline
from src.config import Config
from src.merger import EnrichmentRecord, merge_enrichments
from src.models import HumanPreference, SourceMeta
from src.sources.lmarena import LMArenaAdapter
from src.sources.openrouter import OpenRouterAdapter

_setup_logging()


def anchor():
    return OpenRouterAdapter()._parse_one({
        "id": "example/compact", "name": "Compact", "context_length": 16000,
        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
    })


class PipelineTests(unittest.TestCase):
    def test_empty_output_uses_repo_default(self):
        with patch.dict(os.environ, {"DATASET_OUTPUT_PATH": ""}):
            expected = Path(__file__).resolve().parents[2] / "dataset" / "dataset.json"
            self.assertEqual(Config.load().dataset_output_path, expected)

    def test_price_units_and_invalid_id(self):
        model = anchor()
        self.assertEqual((model.price.input, model.price.output), (1, 2))
        self.assertIsNone(OpenRouterAdapter()._parse_one({"id": "invalid"}))

    def test_merge_preserves_anchor_and_adds_coverage(self):
        record = EnrichmentRecord(
            raw_key="compact", organization="example", source="lmarena",
            human_preference=HumanPreference(arena_elo=1000, arena_rank=1),
        )
        with patch("src.alignment.aligner.candidate_canonical_id", return_value="example/compact"):
            models, report = merge_enrichments([anchor()], {"lmarena": [record]})
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].price.input, 1)
        self.assertEqual(models[0].human_preference.arena_elo, 1000)
        self.assertEqual(models[0].source_coverage, ["openrouter", "lmarena"])
        self.assertEqual(models[0].tier, 2)
        self.assertEqual(report.total_matched("lmarena"), 1)


class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_enrichment_failure_keeps_anchor(self):
        meta = SourceMeta(name="openrouter", last_fetched_at="2026-01-01", model_count=1)
        with patch.object(OpenRouterAdapter, "run", new=AsyncMock(return_value=([anchor()], meta))), \
             patch.object(LMArenaAdapter, "fetch", new=AsyncMock(side_effect=RuntimeError("synthetic failure"))):
            dataset = await run_pipeline()
        self.assertEqual(len(dataset.models), 1)
        self.assertEqual(dataset.sources[1].status, "failed")
        self.assertEqual(dataset.sources[1].model_count, 0)


if __name__ == "__main__":
    unittest.main()
