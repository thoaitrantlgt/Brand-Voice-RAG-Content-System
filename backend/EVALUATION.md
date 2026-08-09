# Blog Quality Evaluation

The runtime evaluation pipeline focuses on writing quality. Retrieval quality is benchmarked separately offline:

| Layer | Framework | Metrics | Default gate |
| --- | --- | --- | ---: |
| Brand voice | DeepEval G-Eval | tone, addressing, vocabulary, structure, CTA, brief adherence, writing quality | 0.80 each |
| RAG quality | Ragas | faithfulness, response relevancy, context precision, context recall, factual correctness | 0.70-0.80 each |

Every blog is one test case containing the complete brief, generated blog, full retrieved chunks, brand profile, and held-out reference article when available. Reference-dependent Ragas metrics are reported as `not_applicable` when no reference exists. Missing retrieval context is a hard failure.

The judge input uses a compact scoring-only view of the brand profile. Ragas caps held-out reference text at 4,000 characters so the default 4K-context local judge can process reference-based metrics; the original reference remains unchanged in the benchmark artifact.

## Setup

Use a separate environment. DeepEval and ChromaDB currently require incompatible major versions of `posthog`, so installing the evaluation packages into `.venv` can break the backend runtime.

```powershell
cd backend
python -m venv .venv-eval
.\.venv-eval\Scripts\python.exe -m pip install -r requirements-eval.txt
```

The default judge is the OpenAI-compatible LM Studio endpoint at `http://127.0.0.1:1234/v1`. Load these models before running evaluation:

- Chat judge: `qwen3.5-2b`
- Embeddings: `text-embedding-nomic-embed-text-v1.5`

Override them with `EVAL_MODEL`, `EVAL_EMBEDDING_MODEL`, `EVAL_API_BASE`, and `EVAL_API_KEY`.
For a remote judge with local embeddings, additionally set `EVAL_EMBEDDING_API_BASE` and `EVAL_EMBEDDING_API_KEY`.

## Run A Batch

Generate fresh benchmark rows first. This step now persists the complete retrieval contexts needed by Ragas.

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\run_tss_generation_benchmark.py --count 5
.\.venv-eval\Scripts\python.exe scripts\run_advanced_evaluation.py --limit 5
```

Outputs are written to `data/eval/advanced_qwen3_5_2b/`:

- `results.json`: scores, thresholds, pass state, and judge reasons for every case.
- `summary.json`: batch pass rate and aggregate results for every metric.
- `report.md`: a compact report for reviewer sign-off.

Use `--skip-brand` or `--skip-ragas` to isolate one layer while debugging. A batch passes only when every enabled layer passes for every included blog.

For long reference-based metrics, load the judge with an 8K or larger context and use `--judge-max-tokens 4096`. Use `--ragas-metrics context_recall factual_correctness` to rerun selected failed metrics without repeating the full batch.
For rate-limited remote judges, use `--metric-delay-seconds 15` or a larger provider-appropriate interval.

## Pytest And CI

Normal backend tests skip model-backed evaluation. Run the real quality gates explicitly:

```powershell
$env:RUN_LLM_EVALS = "1"
.\.venv-eval\Scripts\python.exe -m pytest tests\llm_eval --confcutdir=tests\llm_eval -v
```

CI should start the model endpoint, generate or restore benchmark artifacts containing `retrieved_contexts`, then run this command. Keep the fixed benchmark dataset and model versions unchanged when comparing releases.
