"""Opt-in quality gates backed by the local LLM and embedding server."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

if os.getenv("RUN_LLM_EVALS") != "1":
    pytest.skip("Set RUN_LLM_EVALS=1 to run model-backed evaluation", allow_module_level=True)

pytest.importorskip("deepeval")
pytest.importorskip("ragas")

from app.evaluation.deepeval_brand import DeepEvalBrandEvaluator, build_brand_metrics
from app.evaluation.providers import create_deepeval_openai_model, create_ragas_openai_stack
from app.evaluation.ragas_grounding import RagasGroundingEvaluator, build_ragas_metrics
from scripts.run_advanced_evaluation import build_case


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = Path(os.getenv("EVAL_DATASET_DIR", BACKEND_ROOT / "data/eval/tss_pipeline_v2"))
RESULTS_PATH = Path(
    os.getenv(
        "EVAL_GENERATION_RESULTS",
        BACKEND_ROOT / "data/eval/tss_generation_qwen3_5_2b/generation_results.json",
    )
)
MODEL = os.getenv("EVAL_MODEL", "qwen3.5-2b")
EMBEDDING_MODEL = os.getenv("EVAL_EMBEDDING_MODEL", "text-embedding-nomic-embed-text-v1.5")
BASE_URL = os.getenv("EVAL_API_BASE", "http://127.0.0.1:1234/v1")
API_KEY = os.getenv("EVAL_API_KEY", "lm-studio")


@pytest.fixture(scope="module")
def evaluation_case():
    rows = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    article_map = json.loads((DATASET_DIR / "article_texts.json").read_text(encoding="utf-8"))
    profile = json.loads((DATASET_DIR / "brand_voice_profile.json").read_text(encoding="utf-8"))
    row = next(
        item
        for item in rows
        if item.get("content") and item.get("retrieved_contexts") and not item.get("error")
    )
    return build_case(row, article_map, profile)


@pytest.mark.llm_eval
def test_tss_brand_voice_meets_deepeval_gate(evaluation_case):
    judge = create_deepeval_openai_model(model=MODEL, base_url=BASE_URL, api_key=API_KEY)
    report = DeepEvalBrandEvaluator(build_brand_metrics(judge)).evaluate(evaluation_case)

    failures = {
        name: result
        for name, result in report["metrics"].items()
        if not result["passed"]
    }
    assert report["passed"], json.dumps(failures, ensure_ascii=False, indent=2)


@pytest.mark.llm_eval
@pytest.mark.asyncio
async def test_tss_rag_meets_ragas_gate(evaluation_case):
    llm, embeddings = create_ragas_openai_stack(
        model=MODEL,
        embedding_model=EMBEDDING_MODEL,
        base_url=BASE_URL,
        api_key=API_KEY,
    )
    report = await RagasGroundingEvaluator(build_ragas_metrics(llm, embeddings)).evaluate(
        evaluation_case
    )

    failures = {
        name: result
        for name, result in report["metrics"].items()
        if result["passed"] is False
    }
    assert report["passed"], json.dumps(failures, ensure_ascii=False, indent=2)
