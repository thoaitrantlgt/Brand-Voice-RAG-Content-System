# RankLLM Local Experiment

An offline relevance-ranking feasibility spike, separate from production SEO Readiness.
It does **not** predict Google positions, indexing, clicks or traffic.

## Setup

From `backend/`, with Python 3.12+ and Git:

```powershell
python -m venv .venv-rankllm
.\.venv-rankllm\Scripts\python.exe -m pip install -r evaluation\rankllm\requirements.txt
```

The upstream Git commit is pinned because the PyPI release with the same version
pulled GPU dependencies that failed to install on Windows during this experiment.
Do not add these experimental dependencies to production `requirements.txt`.

LM Studio must serve `qwen3.5-2b` at `http://127.0.0.1:1234/v1`.
The adapter only permits a loopback endpoint and uses a dummy local API key.
The first ranking run may download a public tiktoken vocabulary file.

## Run

Use a new output directory for a new snapshot. Choose an existing generation run
from your database; the example run ID is local to the original experiment.

```powershell
$out = '..\.runtime\rankllm\my-experiment'
.\.venv-rankllm\Scripts\python.exe -X utf8 scripts\run_rankllm_experiment.py prepare --output $out --run-id run_c5f42ee72c594f83
.\.venv-rankllm\Scripts\python.exe -X utf8 scripts\run_rankllm_experiment.py run --output $out --label baseline
.\.venv-rankllm\Scripts\python.exe -X utf8 scripts\run_rankllm_experiment.py run --output $out --label singleturn --prompt-template rank_zephyr_template.yaml
```

`prepare` reads SQLite in read-only mode and fetches the manually selected URLs in
`sources.json`. Inspect the extracted titles/text in `dataset.json` before ranking.
These URLs are not a verified Google top-10 list. One excluded page and its extraction
problem are recorded in the source manifest.

Each configuration runs two queries, three shuffled candidate orders and five
four-document sliding windows per trial when all ten competitors are available.
The pool contains ten web articles, one real generated blog and one synthetic
off-topic control. Blog rank excludes that control, so its denominator is eleven;
control rank uses all twelve candidates.

The Qwen server used in the original trial had 4,096 context tokens. RankLLM uses a
3,000-token prompt budget estimated with tiktoken, a 256-token output limit, and
up to 250 whitespace-separated words from each article's title/prefix. It can
shorten excerpts further to fit. This is **excerpt relevance**, not whole-blog
quality. Tiktoken is an approximate budgeter for Qwen, not its native tokenizer.

The actual RankLLM library owns prompt construction and sliding-window reranking.
The local subclass replaces its Responses API call with Chat Completions, disables
SDK retries, sets a timeout, and rejects malformed/duplicate/missing IDs rather
than accepting the library's repaired permutation. Both templates come from the
pinned upstream package; `/nothink` and an untrusted-passage instruction are appended.

## Artifacts

All runtime artifacts are ignored by Git:

- `dataset.json`: timestamp, source URLs, extracted text, SHA-256 hashes and brief.
- `project-blog.md`: unchanged generated blog.
- `<label>/q*-seed*.json`: shuffled inputs, exact prompts, raw responses, token usage,
  validity, final order and per-window timing.
- `<label>/summary.json` and `report.md`: metrics and limitations.

Existing snapshots/trials are not overwritten. Use a new `--label` to rerun a model
configuration on the same snapshot. To compare an edited blog, add
`--blog-file path\to\revised.md --label revised`, keeping the same queries/seeds.
This does not write the revision back to SQLite.

## Interpretation

- Valid permutation rate measures output syntax, **not accuracy**.
- Negative-control-last rate checks basic topic discrimination. Failure blocks
  treating the rankings as an SEO quality score. Passing alone is insufficient.
- Pairwise order agreement measures repeatability across shuffled orders for the
  same query. It does not measure relevance correctness or compare Google ranks.
- No nDCG/MRR accuracy claims are made without independent relevance labels.
- Before/after article optimization should wait until the judge passes controls
  and is checked against human labels. Do not optimize prose to an unreliable judge.
- No paid API is used, and there are no changes to the production pipeline or UI.

Focused tests from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_rankllm_experiment.py -q
```

References: [RankLLM source](https://github.com/castorini/rank_llm/tree/443adf3306102f11b85945d2a277fb6aa10ea0aa),
[RankLLM paper](https://arxiv.org/abs/2505.19284).
