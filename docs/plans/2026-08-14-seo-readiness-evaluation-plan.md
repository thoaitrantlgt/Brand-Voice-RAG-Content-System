# SEO Readiness Metric and Final Evaluation Plan

> Status: Superseded by [Content SEO Readiness V2](./2026-08-23-content-seo-v2.md)
>
> Date: 2026-08-14
>
> Scope: SEO Readiness V1 is implemented for draft generation and review. Public-page technical SEO remains a separate release phase.

## Implementation status

Implemented in V1:

- SEO brief fields: primary keyword, search intent and optional web research.
- SEO-aware Planner, Writer and Editor instructions.
- Truthful meta description generation from the article and a suggested slug.
- Deterministic six-part SEO Readiness score with checks, field issues and body annotations.
- Worker, final judge, Create and Review UI integration.
- SEO remains informational by default and is excluded from the existing overall score.
- A fixed 25-case benchmark runner is included. Deterministic smoke results are 100% keyword-stuffing recall, 0% stuffing false positives, 100% severe title/meta recall and 0 fabricated annotations on the current fixture.

Calibration caveat: the fixture intentionally contains no fabricated human scores. Spearman correlation remains unavailable until two independent reviewers score every case.

Deferred until the product has crawlable public article pages:

- Canonical URL, robots directives, sitemap and Article structured data validation.
- Lighthouse/Core Web Vitals collection against deployed article URLs.
- Search Console impressions, clicks, CTR and position feedback loop.

## 1. Objective

Add an SEO metric that can:

1. Improve the SEO preparation given to Planner, Writer, and Editor.
2. Evaluate the generated article before human review.
3. Explain why the article received its SEO score.
4. Highlight weak passages inside the final article.
5. Report title and meta-description issues separately from article highlights.
6. Avoid presenting an internal score as a guarantee of ranking in Google Search.

The metric will be named **SEO Readiness**. It measures whether a draft follows useful on-page SEO practices. It does not predict ranking position.

## 2. Research Basis

The implementation should prioritize official Google Search documentation over arbitrary SEO formulas.

Primary references:

- [Google Search Essentials](https://developers.google.com/search/docs/essentials)
- [SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
- [Creating helpful, reliable, people-first content](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)
- [Spam policies and keyword stuffing](https://developers.google.com/search/docs/essentials/spam-policies)
- [Title link best practices](https://developers.google.com/search/docs/appearance/title-link)
- [Meta description and snippet guidance](https://developers.google.com/search/docs/appearance/snippet)
- [Link best practices](https://developers.google.com/search/docs/crawling-indexing/links-crawlable)
- [Article structured data](https://developers.google.com/search/docs/appearance/structured-data/article)
- [Search Console Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)
- [Google Chrome Lighthouse scoring](https://github.com/GoogleChrome/lighthouse/blob/master/docs/scoring.md)
- [Core Web Vitals](https://web.dev/articles/vitals)

Key conclusions:

- There is no guaranteed recipe for ranking first.
- Google recommends helpful, reliable, people-first content.
- Important search terms should appear naturally in prominent locations.
- Keyword stuffing must be treated as a negative signal.
- Google does not define a preferred article word count.
- Google does not define a fixed title or meta-description character limit. Search results can be truncated based on device width and query context.
- Google can generate title links and snippets from several parts of a page, not only the supplied metadata.
- Structured data can make a page eligible for rich results but cannot guarantee that rich results will appear.
- Draft quality and observed search performance are separate measurements.

The system must not implement hard rules such as:

- Keyword density must be between 1% and 2%.
- Every title must be shorter than exactly 60 characters.
- Every meta description must be shorter than exactly 160 characters.
- Longer articles automatically receive a better SEO score.

Character counts may be displayed as advisory UI information, but they must not be treated as direct Google ranking rules.

## 3. Current Repository Gaps

The current pipeline already stores:

- `planned_title`
- `planned_seo_title`
- `title_tag`
- `meta_description`
- Keywords from the content brief

However, the following gaps remain:

1. `ContentService` creates a generic meta description using `Blog post about ...`.
2. `EditorAgent` is described as an SEO specialist, but no SEO score validates its output.
3. `QualityGate` only gates Brand, Style, and Fingerprint.
4. `FinalEvaluationService` does not have an SEO metric contract.
5. The frontend has no dedicated SEO report or SERP preview.
6. Publishing only inserts a row into SQLite. It does not create a public, crawlable blog page.
7. There is no slug, canonical URL, sitemap, robots policy, Article JSON-LD, or Search Console integration.

Relevant modules:

```text
backend/app/services/content_service.py
backend/app/services/quality_gate.py
backend/app/services/final_evaluation_service.py
backend/app/workers/job_worker.py
backend/app/repositories/generation_repository.py
backend/app/tasks/planner_task.py
backend/app/tasks/writer_task.py
backend/app/tasks/editor_task.py
frontend/app/components/FinalEvaluation.tsx
frontend/app/create/page.tsx
frontend/app/review/page.tsx
```

## 4. Metric Boundary

SEO evaluation must be split into two independent layers.

### 4.1 Draft SEO Readiness

Measured before human review using the article, brief, title, metadata, and target keywords.

This layer can evaluate:

- Search intent alignment
- Topic coverage
- Title and H1 quality
- Meta-description quality
- Keyword placement and naturalness
- Heading structure
- Helpfulness and content completeness

### 4.2 Published Technical SEO

Measured only after a public URL exists.

This layer can evaluate:

- Crawlability and indexability
- Canonical URL
- Sitemap and robots directives
- Server-rendered metadata
- Article structured data
- Internal links
- Image metadata and alt text
- Lighthouse SEO audits
- Core Web Vitals
- Search Console impressions, clicks, CTR, and average position

When no public URL exists, technical SEO must return `not_applicable` or `unavailable`. It must not reduce the draft SEO score to zero.

## 5. SEO Readiness Scoring Contract

The SEO Readiness score is a number from 0 to 100.

```text
SEO Readiness =
    25% Search intent alignment
  + 20% Helpful topic coverage
  + 15% Title and H1 quality
  + 10% Snippet quality
  + 15% Keyword usage quality
  + 15% Content structure
```

### 5.1 Search Intent Alignment - 25 points

Evaluate whether the article answers the need represented by:

- Topic
- Primary keyword
- Audience
- Objective
- Explicit search intent

Checks:

- The title and H1 describe the same problem as the brief.
- The introduction confirms what the reader will learn.
- The article answers the expected informational, commercial, navigational, or transactional intent.
- The conclusion does not introduce an unrelated objective.

Evaluation method:

- Deterministic topic and keyword overlap checks.
- LLM judge for intent correctness and title-content mismatch.

### 5.2 Helpful Topic Coverage - 20 points

Evaluate whether the reader can complete the intended task without immediately searching again.

Checks:

- Required brief points are covered.
- Important steps, explanations, or examples are present.
- The article contains actionable information rather than generic filler.
- Claims do not overpromise or pretend to answer questions with unavailable facts.
- Content adds value instead of merely repeating the same idea.

Evaluation method:

- Existing `must_cover` logic.
- Outline-to-content section coverage.
- LLM judge for usefulness and completeness.

### 5.3 Title and H1 Quality - 15 points

Checks:

- Exactly one H1 exists.
- The H1 and SEO title are aligned with the topic.
- The title accurately summarizes the article.
- The title is descriptive and concise.
- The title avoids clickbait, vague wording, boilerplate, and keyword repetition.
- The title is distinct from existing titles in the same project.

Title length is advisory only. A long title can receive a warning that it may be truncated, but length alone is not a ranking failure.

### 5.4 Snippet Quality - 10 points

Checks:

- A meta description exists.
- It accurately summarizes the final article.
- It is specific to the current page.
- It is not a raw list of keywords.
- It is not duplicated across project blogs.
- It contains the primary topic naturally when useful.

Meta-description length is advisory only. The UI may show a preview and truncation warning, but the evaluator must prioritize accuracy and uniqueness.

### 5.5 Keyword Usage Quality - 15 points

Checks:

- The primary keyword or a close natural variation appears in prominent content.
- Important secondary keywords are covered where relevant.
- Keywords are distributed naturally instead of appearing as a block.
- Repetition does not make sentences unnatural.
- The article does not contain keyword stuffing.

The system must not target a fixed keyword density. It should detect unnatural repetition using placement, repeated phrases, local repetition windows, and model judgment.

### 5.6 Content Structure - 15 points

Checks:

- H2 and H3 hierarchy is valid.
- Headings describe the content beneath them.
- Sections are easy to scan.
- Paragraphs are not excessively repetitive or unbroken.
- Lists and steps are used where they improve comprehension.
- Introduction, main content, and conclusion have clear roles.

## 6. Score Interpretation

Initial UI interpretation:

| Score | Status | Meaning |
| ---: | --- | --- |
| 80-100 | Good | Ready for SEO review and publishing workflow |
| 65-79 | Needs improvement | Reviewer should inspect identified issues |
| 0-64 | Weak | Major intent, metadata, keyword, or structure problems |

Recommended rollout:

- V1: SEO is informational with `gated=false`.
- Display reference threshold `75` while collecting benchmark evidence.
- Severe deterministic checks can still create explicit violations.
- After calibration, enable an optional `SEO_GATE_ENABLED` setting.
- Do not add SEO to the existing overall quality average during V1.

Severe checks:

- Missing SEO title
- Missing or generic meta description
- Title and article discuss different topics
- Keyword stuffing
- Invalid H1 structure

## 7. Evaluation Architecture

Create a new service:

```text
backend/app/services/seo_evaluation_service.py
```

Proposed responsibilities:

```python
class SeoEvaluationService:
    def evaluate(
        self,
        *,
        content: str,
        brief: dict,
        planned_title: str,
        seo_title: str,
        meta_description: str,
        existing_project_blogs: list[dict],
    ) -> dict:
        ...
```

The service combines:

1. Deterministic checks for stable structural evidence.
2. Optional LLM evaluation for search intent and helpfulness.
3. Exact evidence that can be displayed or highlighted.

The LLM must not freely replace deterministic values. It should only score the dimensions assigned to model judgment.

## 8. Output Schema

Store the SEO result under the generation quality report. No database migration is required for V1 because `quality_report_json` already stores structured JSON.

```json
{
  "dimension_scores": {
    "brand": 84,
    "style": 90,
    "fingerprint": 68,
    "persona": 74,
    "seo": 78
  },
  "seo_evaluation": {
    "status": "evaluated",
    "score": 78,
    "threshold": 75,
    "gated": false,
    "included_in_overall": false,
    "subscores": {
      "search_intent": 84,
      "helpful_coverage": 76,
      "title_h1": 90,
      "snippet": 55,
      "keyword_usage": 72,
      "structure": 82
    },
    "checks": [
      {
        "code": "generic_meta_description",
        "status": "failed",
        "severity": "warning",
        "evidence": "Blog post about ...",
        "recommendation": "Write a page-specific summary of the article."
      }
    ],
    "field_issues": [
      {
        "field": "meta_description",
        "current_value": "Blog post about ...",
        "reason": "The description is generic and does not summarize this article.",
        "suggestion": "Summarize the practical result and primary topic in one natural sentence."
      }
    ],
    "annotations": []
  }
}
```

`field_issues` is required because title and meta-description text may not exist inside the article body. These issues must not be forced into article annotations.

## 9. Pipeline Changes

Target workflow:

```text
User brief
  -> resolve primary keyword and search intent
  -> optional SEO research
  -> build SEO brief
  -> Planner creates title, SEO title, and outline
  -> Writer creates article
  -> Editor improves article
  -> create SEO package
  -> run SeoEvaluationService
  -> run targeted rewrite for severe SEO issues
  -> run Brand, Style, Fingerprint, and Persona evaluation
  -> final judge explains every metric
  -> show final SEO section
  -> human review
```

### 9.1 Brief Changes

Extend `ContentBrief` with:

```python
primary_keyword: str | None = None
search_intent: Literal["auto", "informational", "commercial", "navigational", "transactional"] = "auto"
seo_research_enabled: bool = False
```

Backward compatibility:

- If `primary_keyword` is missing, use the first item in `keywords`.
- Existing API clients remain valid.

### 9.2 Optional SEO Research

Reuse the existing web-search provider instead of scraping Google result pages directly.

Collect only:

- Top result titles
- Result snippets
- Common questions
- Repeated entities and subtopics
- Content gaps

Store a derived `seo_brief`. Do not copy competitor paragraphs into the generated article.

Suggested output:

```json
{
  "intent": "informational",
  "primary_keyword": "cách giữ hơi khi hát",
  "secondary_topics": ["tư thế", "cơ hoành", "bài tập xì hơi"],
  "questions": ["Vì sao hát nhanh hết hơi?"],
  "coverage_gaps": ["bài tập cho người mới"],
  "source_urls": []
}
```

### 9.3 SEO Package Generation

Replace the current generic metadata fallback with a structured SEO package:

```json
{
  "seo_title": "...",
  "meta_description": "...",
  "suggested_slug": "...",
  "primary_keyword": "...",
  "search_intent": "informational"
}
```

Metadata must be generated from the final article, not from the initial outline alone.

### 9.4 Rewrite Loop

SEO issues should be passed to the existing targeted rewrite loop only when the article body can fix them.

Examples:

- `seo_intent_mismatch`
- `seo_keyword_stuffing`
- `seo_heading_structure`
- `seo_helpfulness_below_threshold`

Metadata-only issues should regenerate the SEO package instead of rewriting the full article.

Brand Voice constraints remain higher priority than aggressive keyword placement. SEO optimization must not remove required terminology or force an unnatural tone.

## 10. Final Evaluation Integration

Extend the final evaluator metric contract:

```json
{
  "seo": "Informational SEO Readiness metric in V1; explain intent, title, snippet, keyword use, and structure."
}
```

Final judge responsibilities:

- Preserve the SEO score calculated by `SeoEvaluationService`.
- Explain each SEO subscore in Vietnamese.
- Highlight exact article passages that are repetitive, irrelevant, vague, or stuffed with keywords.
- Return no fabricated quote.
- Report title and metadata problems through `field_issues`.

The final judge must not claim that the article will rank at a specific position.

## 11. Frontend Plan

Create:

```text
frontend/app/components/SeoEvaluation.tsx
```

Display the SEO section after the existing final evaluation.

Required UI elements:

- SEO Readiness score from 0 to 100
- Informational/gated status
- Six subscore bars
- SERP-style title and snippet preview
- Character counts marked as advisory
- Passed, warning, and failed checks
- Field-specific title/meta recommendations
- Exact highlighted article passages
- Short disclaimer that the score is not a ranking guarantee

Update:

```text
frontend/app/create/page.tsx
frontend/app/review/page.tsx
frontend/app/components/FinalEvaluation.tsx
```

Do not duplicate the full SEO report in both Quality and Final Evaluation panels. Use one reusable component.

## 12. Technical SEO Phase

The current publish action stores content in SQLite but does not expose a crawlable blog page. If AI Content OS will host published blogs, add:

```text
frontend/app/blog/[slug]/page.tsx
frontend/app/sitemap.ts
frontend/app/robots.ts
```

Database additions:

```text
blogs.slug
blogs.canonical_url
blogs.published_url
blogs.og_image_url
blogs.schema_json
```

Public page requirements:

- Server-rendered article HTML
- Unique `<title>`
- Meta description
- Canonical link
- Open Graph metadata
- `Article` or `BlogPosting` JSON-LD
- Author and publication date
- Relevant image metadata
- Crawlable internal links
- Inclusion in sitemap

If publishing goes to an external CMS instead, implement a publishing adapter that sends the same SEO package to WordPress, Webflow, or the target CMS. Do not add a duplicate public route inside ContentOS.

## 13. Post-Publish SEO Audit

Post-publish SEO must remain separate from SEO Readiness.

Proposed output:

```json
{
  "technical_seo": {
    "status": "evaluated",
    "lighthouse_score": 92,
    "crawlable": true,
    "canonical_valid": true,
    "structured_data_valid": true
  },
  "observed_performance": {
    "period_days": 28,
    "impressions": 1200,
    "clicks": 84,
    "ctr": 0.07,
    "average_position": 11.4
  }
}
```

Use:

- Lighthouse for rendered technical checks.
- Rich Results Test and URL Inspection during release validation.
- Search Console API for impressions, clicks, CTR, queries, and average position.

Search Console data is the source of truth for search performance. It must not be merged into the pre-publication content score.

## 14. Configuration

Proposed settings:

```env
SEO_EVALUATION_ENABLED=true
SEO_LLM_JUDGE_ENABLED=false
SEO_GATE_ENABLED=false
SEO_GATE_THRESHOLD=75
SEO_RESEARCH_ENABLED=false
SEO_RESEARCH_TOP_K=5
SEO_DUPLICATE_TITLE_CHECK=true
SEO_DUPLICATE_META_CHECK=true
```

The optional local vLLM judge is disabled by default to keep runtime latency deterministic. Enable it for smoke/calibration runs before comparing a cloud/API judge on the same fixed dataset.

## 15. Testing Plan

### 15.1 Unit Tests

Add:

```text
backend/tests/test_seo_evaluation_service.py
backend/tests/test_seo_workflow.py
backend/tests/test_final_evaluation_service.py
```

Minimum cases:

1. Good informational article.
2. Missing primary keyword in all prominent locations.
3. Natural keyword variation.
4. Keyword stuffing.
5. Multiple H1 headings.
6. Invalid H2/H3 hierarchy.
7. Title-content mismatch.
8. Clickbait title.
9. Missing meta description.
10. Generic meta description.
11. Duplicate title in the same project.
12. Duplicate meta description in the same project.
13. Shallow article with filler.
14. Good article with no exact-match keyword but correct semantic intent.
15. Metadata issue that must not trigger a full article rewrite.

### 15.2 Frontend Tests

Verify:

- Score and subscores render correctly.
- Long titles do not overflow.
- SERP preview is responsive.
- Article annotations map to exact text.
- Metadata issues render without fake article positions.
- `not_applicable` technical SEO does not appear as a zero score.

### 15.3 Benchmark Dataset

Create at least 25 Vietnamese SEO cases with:

- Topic
- Primary keyword
- Search intent
- Audience
- Reference outline
- Positive article
- Negative or manipulated article
- Human SEO score
- Human issue labels

Use at least two human reviewers.

Initial acceptance targets:

| Measure | Target |
| --- | ---: |
| Correlation with mean human SEO score | Spearman >= 0.65 |
| Keyword-stuffing recall | >= 90% |
| Keyword-stuffing false-positive rate | <= 5% |
| Severe title/meta issue recall | >= 90% |
| Score variation across three model runs | <= 3 points |
| Fabricated article annotations | 0 |

## 16. Rollout Plan

### Phase 0 - Repository Sync

- Sync local `main` with remote because the local branch is currently behind by one commit.
- Review the remote commit before editing shared files.
- Re-run the existing backend and frontend baseline.

### Phase 1 - Deterministic SEO Metric

- Add schemas and `SeoEvaluationService`.
- Implement title, meta, keyword, heading, duplicate, and structure checks.
- Store `seo_evaluation` in `quality_report_json`.
- Keep `gated=false`.

### Phase 2 - Generation Optimization

- Add primary keyword and search intent to the brief.
- Generate a real SEO package after article generation.
- Add optional SEO research.
- Add body rewrite and metadata-regeneration paths.

### Phase 3 - Final Evaluation and UI

- Add SEO to the final judge contract.
- Add exact SEO annotations.
- Add metadata field issues.
- Build the final SEO evaluation panel and SERP preview.

### Phase 4 - Calibration

- Run 25-case benchmark locally with Qwen.
- Compare against human scores.
- Adjust weights and thresholds using evidence.
- Test an API judge only after the local path is stable.

### Phase 5 - Technical SEO

- Confirm whether ContentOS or an external CMS hosts public blogs.
- Add crawlable publishing or a CMS adapter.
- Add Lighthouse, structured data, sitemap, canonical, and Search Console integration.

## 17. Definition of Done

SEO V1 is complete when:

- Every terminal generation attempt contains `seo_evaluation`.
- The SEO score is reproducible for deterministic checks.
- The score has six documented subscores.
- The generic `Blog post about ...` meta fallback is removed.
- Final evaluation explains the SEO result without changing the fixed score.
- Article SEO issues map to exact text positions.
- Title/meta issues render as field issues.
- SEO does not modify the existing overall quality score in V1.
- SEO does not block publish until benchmark calibration is accepted.
- All backend tests pass.
- Frontend lint and production build pass.
- The 25-case SEO benchmark meets the agreed acceptance thresholds.
- Documentation clearly states that SEO Readiness is not a ranking guarantee.

## 18. Implementation Checklist

- [x] Sync and review remote `main`.
- [x] Add SEO settings.
- [x] Extend `ContentBrief`.
- [x] Add SEO output schema in `quality_report_json`.
- [x] Implement deterministic SEO evaluator.
- [x] Add optional LLM intent/helpfulness evaluator.
- [x] Replace generic metadata generation.
- [x] Integrate SEO evaluation into worker workflow.
- [x] Add targeted SEO rewrite feedback for optional gated mode.
- [x] Add SEO contract to final evaluator.
- [x] Add exact article annotations.
- [x] Add metadata field issues.
- [x] Add frontend SEO panel.
- [x] Add SERP preview.
- [x] Add backend unit tests.
- [x] Pass frontend lint and production build.
- [x] Build 25-case Vietnamese benchmark fixture and runner.
- [ ] Calibrate weights and threshold.
- [ ] Decide public Next.js route versus CMS publishing adapter.
- [ ] Add technical SEO and Search Console only after a public URL exists.
