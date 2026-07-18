# README Redesign Specification

## Goal

Replace the current long, partially outdated README with a polished English product-and-developer guide. A new contributor should understand the product, run it locally, and find deeper evaluation material without reading implementation code.

## Audience

- Content and engineering teams evaluating the product.
- Developers installing or operating the internal stack.
- Reviewers assessing architecture, safeguards, and current quality evidence.

## Structure

1. Centered product header with concise tagline and technology/test badges.
2. Product value and the two-cluster data model: factual knowledge versus approved brand samples.
3. Mermaid diagram of the project-scoped asynchronous generation workflow.
4. Feature summary tied to the actual application routes.
5. PowerShell-first quick start, including LM Studio, secure auth, and local-only insecure mode.
6. Current architecture, repository layout, and primary asynchronous API endpoints.
7. Evaluation evidence from the verified TSS smoke run, clearly separating operational success from the unmet release benchmark.
8. Testing, readiness, backup, Docker, security, and release checklist.
9. Links to detailed pipeline and benchmark documents instead of duplicating their full contents.

## Content Rules

- Write entirely in English.
- Target roughly 300 to 400 lines and optimize for scanning.
- Describe only behavior present in the current repository.
- Treat asynchronous project-scoped APIs as the supported workflow; identify synchronous APIs as disabled legacy behavior.
- Do not claim the product has passed the 25-topic quality release gate.
- Preserve verified figures: 50 backend tests, Qwen3.5-2B readiness, and the documented TSS smoke scores.
- Use restrained badges, tables, code blocks, and Mermaid diagrams. Do not add stock imagery or decorative assets.

## Verification

- Scan headings and links for a coherent reading order.
- Search for stale model names and legacy endpoint recommendations.
- Confirm all referenced local files and commands exist.
- Run Markdown-oriented textual checks and inspect the final Git diff.
