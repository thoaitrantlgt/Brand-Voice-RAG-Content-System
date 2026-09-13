# RankLLM + Local Qwen: SEO Feasibility Experiment

## Decision

**Do not use this configuration as a customer-facing SEO ranking score.**
The integration works, but the tested Qwen 3.5 2B configuration failed a basic
off-topic control and produced unstable document rankings. This does not establish
that the blog is good or bad, or that RankLLM fails with other models.

## Setup

- Date: 2026-09-12.
- Model: LM Studio `qwen3.5-2b`, Q4_K_M, loaded context 4,096 tokens.
- Library: [RankLLM](https://github.com/castorini/rank_llm/tree/443adf3306102f11b85945d2a277fb6aa10ea0aa), pinned commit `443adf3306102f11b85945d2a277fb6aa10ea0aa`.
- Blog: `run_c5f42ee72c594f83`, 5,710 characters, read from the existing generation database.
- Blog heading: "Huong Dan Kiem Soat Hoi Khi Hat Cho Nguoi Moi Bat Dau" (original Vietnamese text retained in the snapshot).
- Pool: 10 public web articles + the generated blog + a synthetic SQLite backup paragraph.
- Sources: GoChek, Unica, Yamaha, Canhacnhe, Duytieu Music, Yokara, ADAM Muzic, Viet Thuong, Piano House, SEAMI. URLs are in the [manifest](../../backend/evaluation/rankllm/sources.json).
- Two Vietnamese queries: beginner singing breath control; at-home singing breath exercises.
- Three shuffled orders per query: seeds 17, 42, 93.
- Two upstream prompt formats: RankGPT multi-turn and RankZephyr single-turn, both served by the same Qwen model. RankZephyr here is a prompt name, not a second loaded model.
- Twelve main trials, five windows each: **60 local model calls**. An additional five-call smoke test is excluded from the table below.
- Each window: four documents, stride two, at most 250 whitespace-separated words per title/prefix, automatically shortened to a 3,000-token estimated input budget.
- Temperature zero, 256 output tokens; no paid/cloud API calls.

## Results

| Measure | Multi-turn | Single-turn |
|---|---:|---:|
| Main trials | 6 | 6 |
| Syntactically valid window outputs | 30/30 | 30/30 |
| Valid complete trial permutations | 6/6 | 6/6 |
| Off-topic control ranked last | **0/6** | **0/6** |
| Pairwise order agreement across shuffles | **41.8%** | **38.8%** |
| Blog rank range among 11 articles | 2-10 | 2-11 |
| First selected window position is ID 3 | 29/30 | 30/30 |

Blog ranks below **exclude** the synthetic control. They are observed experimental
outputs, not trusted quality judgments and never Google positions.

| Query | Seed | Multi-turn blog rank | Single-turn blog rank |
|---|---:|---:|---:|
| Beginner breath control | 17 | 5/11 | 5/11 |
| Beginner breath control | 42 | 10/11 | 11/11 |
| Beginner breath control | 93 | 2/11 | 5/11 |
| At-home breath exercises | 17 | 6/11 | 2/11 |
| At-home breath exercises | 42 | 10/11 | 11/11 |
| At-home breath exercises | 93 | 5/11 | 5/11 |

The unrelated SQLite paragraph finished at position 8 or 10 out of 12 in every
main trial, above multiple relevant articles. ID 3 was selected first in 59/60
windows despite shuffled content, a strong warning of positional behavior in this
setup. Sliding-window mechanics also contribute to dependence on input order.

Pairwise agreement is the fraction of article pairs ordered alike across two
shuffles of the same query, averaged across the six within-query comparisons per
prompt format. It measures repeatability, **not relevance accuracy**. No human
labels were collected, so nDCG/MRR accuracy is not reported.

## Implications

The negative-control failure blocks meaningful before/after article optimization
using this judge. No revised blog was generated or promoted based on these ranks.
Changing only the prompt format did not resolve the issue in this experiment.

Before integration, test another judge on this fixed snapshot, include independently
labeled relevance examples, and rerun both the negative-control and order-sensitivity
checks. Keep the label "experimental relevance ranking" even after those checks pass.
Google ranking and traffic still require real publication and search-performance
observations; article excerpts omit domain, indexing, link and behavioral signals.

## Artifacts And Verification

- [Reproduction instructions](../../backend/evaluation/rankllm/README.md).
- [Experiment script](../../backend/scripts/run_rankllm_experiment.py).
- Local snapshot and exact model prompts: `.runtime/rankllm/2026-09-12/verified/`.
- Per-trial JSON and generated summaries: `baseline/` and `singleturn/` under that directory.
- Article snapshots/model prompts are ignored by Git; this report and source manifest are retained.
- Focused parser/order-agreement checks: **9 passed**.
- No production pipeline/UI changes, database writes, commits or pushes were performed for this experiment.
- This experiment is not a full regression test of the existing SEO implementation.
