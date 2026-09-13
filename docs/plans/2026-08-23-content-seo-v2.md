# Content SEO Readiness V2

> Status: implemented in the draft-generation pipeline on 2026-08-23
>
> Scope: pre-publish content quality, structured web-research provenance, and benchmark calibration

## 1. Product boundary

SEO is split into three independent products. A missing public URL must never make a draft score zero.

| Layer | When | Inputs | Output |
|---|---|---|---|
| Content SEO Readiness V2 | Before publish | Brief, article, title, meta, project duplicates | Explainable 0-100 readiness score |
| Technical SEO | After a public page exists | Rendered HTML and public URL | Crawlability, canonical, structured data, Lighthouse |
| Observed Search Performance | After indexing and traffic | Search Console and analytics | Impressions, clicks, CTR, queries, landing-page outcomes |

The V2 score is informational by default, excluded from the overall brand-quality score, and does not predict rank.

## 2. Research basis

Primary sources:

- [Google: Creating helpful, reliable, people-first content](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)
- [Google: AI features and your website](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
- [Google: Spam policies](https://developers.google.com/search/docs/essentials/spam-policies)
- [Google: Crawlable link best practices](https://developers.google.com/search/docs/crawling-indexing/links-crawlable)
- [Google: Article structured data](https://developers.google.com/search/docs/appearance/structured-data/article)
- [Google: Search Console and Google Analytics](https://developers.google.com/search/docs/monitor-debug/google-analytics-search-console)
- [Lighthouse scoring model](https://github.com/GoogleChrome/lighthouse/blob/master/docs/scoring.md)

Implementation conclusions:

- Exact query matching is not required. Semantic fulfillment of the reader's need matters more than repeating a phrase.
- Keyword stuffing is a negative guardrail, not an optimization target. There is no target keyword-density formula.
- Useful specificity, original observations, examples, and transparent evidence deserve independent evaluation.
- Title and snippet should accurately represent the page. Character counts remain advisory because Google can rewrite or truncate them by context.
- There is no special generative-engine optimization switch. Content that is accessible, helpful, and technically sound remains the stable foundation.
- Competitor research supplies topic context and source leads. It must not be copied into the generated article.

## 3. Score contract

```text
Content SEO Readiness V2 =
    20% Search Intent Satisfaction
  + 20% Helpful Completeness
  + 15% Information Gain & Originality
  + 15% Evidence, Expertise & Trust
  + 10% Title & Snippet Accuracy
  + 10% Semantic Topic Coverage
  + 10% Structure & Scannability
```

Default readiness threshold: `75/100`.

Hard caps still protect against severe mechanical defects:

- Missing SEO title
- Missing or invalid H1
- Title-content mismatch
- Keyword repetition consistent with stuffing
- Missing or generic meta description

### 3.1 Search Intent Satisfaction - 20%

Question: does the article solve the need represented by the topic, audience, objective, and declared or inferred intent?

Signals:

- H1 and introduction make the answer or outcome clear.
- Informational, commercial, transactional, and navigational content use the appropriate form.
- The article does not switch to an unrelated goal.
- Optional LLM judge evaluates intent fulfillment without changing mechanical title or structure checks.

### 3.2 Helpful Completeness - 20%

Question: can the intended reader act or decide without immediately searching for the missing core step?

Signals:

- `must_cover` requirements are represented.
- Topic and objective are covered in the body.
- Main sections are present.
- The answer contains usable guidance rather than generic filler.

### 3.3 Information Gain & Originality - 15%

Question: does this page add specific value beyond a commodity summary?

Deterministic signals currently include:

- Concrete numbers or measurements
- Worked examples or named situations
- First-hand observations or process details
- Step sequences, comparisons, and checkpoints
- Sufficient detail to make the advice usable

The optional judge evaluates whether those details genuinely add value. It must not reward invented experience.

### 3.4 Evidence, Expertise & Trust - 15%

Question: are important claims supportable and are limitations represented honestly?

Signals:

- Links or named attribution for claims that need support
- First-hand experience stated as experience, not universal fact
- Safety boundaries and limitations where relevant
- Clear distinction between advice and professional diagnosis

Not every low-stakes blog requires citations. The score rewards appropriate evidence; it does not impose citations mechanically on every paragraph.

### 3.5 Title & Snippet Accuracy - 10%

Question: do the SEO title, H1, and meta description accurately summarize the final article?

Checks:

- One H1
- Title-H1 promise consistency
- Natural topic representation, including semantic variants
- Non-generic and project-unique title/meta
- Character count displayed only as an advisory

### 3.6 Semantic Topic Coverage - 10%

Question: are the important concepts covered even when the article uses natural wording instead of the exact keyphrase?

The service accepts an injected semantic-similarity function. It combines semantic similarity with lexical coverage and uses the stronger signal. Without an embedding scorer, it falls back to token coverage over topic, objective, primary keyword, and `must_cover` concepts.

The local or API LLM judge also scores semantic coverage. Exact keyword insertion is never required solely to improve this metric.

### 3.7 Structure & Scannability - 10%

Question: can readers and parsers understand the document hierarchy efficiently?

Checks:

- Exactly one H1
- At least two useful H2 sections for normal articles
- No skipped heading hierarchy
- No excessively long, hard-to-scan paragraph

## 4. Structured web research

When `seo_research_enabled=true`, both Planner and Writer may use web search. The system stores provenance in the final quality report:

```json
{
  "query_variations": ["people first SEO"],
  "sources": [
    {
      "query": "people first SEO",
      "title": "Google helpful content",
      "url": "https://developers.google.com/search/docs/helpful",
      "snippet": "Create helpful, reliable, people-first content.",
      "domain": "developers.google.com"
    }
  ],
  "source_urls": ["https://developers.google.com/search/docs/helpful"]
}
```

URLs are deduplicated. Legacy `search_links` remains available for compatibility. The Create and Review screens display source provenance with the search query that found each source.
Planner provenance is persisted when the outline is saved, then merged with Writer provenance in the terminal quality report.

## 5. Optional LLM judge

The judge only blends the five subjective dimensions:

- Search Intent Satisfaction
- Helpful Completeness
- Information Gain & Originality
- Evidence, Expertise & Trust
- Semantic Topic Coverage

Title/meta accuracy, H1 count, duplication, stuffing, and structure remain deterministic.

The response must contain all five judge fields. Missing fields reject the model response and preserve every deterministic score. Brief and article text are sent as untrusted delimited data behind a system instruction, reducing prompt-injection risk. Judge initialization and runtime failures do not stop the worker; deterministic SEO evaluation remains available.

LM Studio can be configured independently from the generation provider:

```env
SEO_LLM_JUDGE_ENABLED=true
SEO_LLM_JUDGE_PROVIDER=openai
SEO_LLM_JUDGE_MODEL=qwen3.5-2b
SEO_LLM_JUDGE_API_BASE=http://127.0.0.1:1234/v1
SEO_LLM_JUDGE_API_KEY=lm-studio
```

This lets Planner and Writer use Google, OpenAI, or vLLM while SEO judging uses a local OpenAI-compatible server.

## 6. Evaluation and calibration

The fixed benchmark contains 25 cases and reports:

- Keyword-stuffing recall
- Keyword-stuffing false-positive rate
- Severe title/meta recall
- Fabricated annotation count
- Spearman rank correlation against human scores
- Mean absolute error against human scores

Two independent human scores with distinct `reviewer_id` values are required for every case before calibration can be marked ready. Until every case is complete, correlation and MAE remain `null`; the benchmark must not publish misleading partial statistics or invent labels and reviewer scores.

Current deterministic smoke result:

```text
keyword stuffing recall:        1.00
keyword stuffing false positive: 0.00
severe title/meta recall:       1.00
fabricated annotations:         0
human calibration:              pending
```

## 7. Deferred work

Technical SEO requires a deployed, crawlable page and remains out of the draft score:

- Canonical URL and robots directives
- Sitemap membership
- Server-rendered title and meta
- Article JSON-LD validation
- Internal-link graph and image alt text
- Lighthouse SEO and performance audits
- Core Web Vitals

Observed performance requires Search Console/analytics access:

- Query and page impressions
- Clicks and CTR
- Average position as a diagnostic, not a content-quality score
- Conversion or engagement outcomes
- Time-windowed comparison after meaningful edits
