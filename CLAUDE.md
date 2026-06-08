# CLAUDE.md

## Project Overview

StoryForge3 is a Chinese web-novel full-workflow creation engine. It supports creating a book from a blank page, building world and character context, planning volumes, and producing single or multi-chapter runs through audit, revision, truth extraction, and export.

## Commands

```powershell
cd D:\python\Novel\storyforge3
& .\.venv\Scripts\python.exe -m pytest
& .\.venv\Scripts\python.exe scripts\e2e_test.py
& .\.venv\Scripts\python.exe scripts\e2e_multi_chapter.py
storyforge3 health
storyforge3 serve
ruff check .
```

## Architecture

### CC-Switch Provider Management

StoryForge3 treats CC-Switch as the source of provider truth and keeps its own project-local selection layer:

```text
CC-Switch SQLite database
    -> CCSwitchDBReader reads providers in read-only mode
    -> ProviderConfigManager imports selected providers into .storyforge3/providers.json
    -> LLMService calls provider routes with multi-endpoint and multi-protocol failover
```

StoryForge3 never writes CC-Switch files. CC-Switch owns its own configuration and database; SF3 only reads the SQLite provider database and persists its own imported provider profiles under `.storyforge3/`.

Current provider example:

- Provider: `Codex 直连中转`
- Base URL: `https://api.vip1129.cc`
- Model: `gpt-5.5`
- Primary route: `{base_url}/v1/responses`

`LLMService` supports OpenAI Chat, OpenAI Responses, Anthropic Messages, and Gemini native requests. It builds route candidates from imported endpoint candidates, strips compatibility suffixes, classifies provider errors, retries rate limits and transient 5xx failures, and can fall back to another imported provider.

### Model Routing

Layer 1 is project provider selection through `.storyforge3/providers.json`. Layer 2 is StoryForge3 task routing through `StoryForge3Config.model_for_task()`, so writer, auditor, truth extractor, architect, and planner tasks can use task-specific model overrides or fall back to the active imported provider model.

### Content Model

StoryForge3 keeps three distinct content layers:

- Machine truth: SQLite `truth_entries` plus JSON backup.
- Author control: book/world/character/context `*.md` and JSON control files.
- Prose: generated chapters under `chapters/*.md`.

### Quality Loop

The chapter loop is:

```text
draft -> normalize -> audit -> revise loop (max 2) -> human confirm -> truth extract -> export
```

Draft and revision payloads include world, character, and relevant truth context to reduce role drift and continuity breaks.

### Service Boundary

The 11 service protocols in `src/storyforge3/services/protocols.py` keep business logic ready for CLI, web, or desktop frontends.
FastAPI exposes these services through REST routes plus `/api/events` SSE, and `storyforge3 serve` starts the API server.

## Service Layer

Core services:

- `BookService`
- `WorldService`
- `CharacterService`
- `VolumeService`
- `ChapterService`
- `AuditService`
- `TruthService`
- `ExportService`
- `DaemonService`
- `StyleService`
- `PromptService`

## Quality Gates

- 36 mechanical audit rules.
- 4 LLM audit dimensions: OOC, power consistency, information boundary, plot logic.
- 5 revision modes: polish, spot_fix, anti_detect, surgical, rework.
- Hook and payoff diagnostics for long-span pacing.
- Blocking audit issues trigger revise and re-audit, up to 2 rounds.

## Export Formats

Supported export formats:

- Tomato TXT
- Markdown collection
- EPUB
- Qidian TXT

## Current Validation

- Unit suite baseline: 266 passed, 91% coverage, `ruff check .` clean.
- FastAPI Phase 1 is complete: health, books, world, characters, volumes, chapters, truth, export, providers, daemon, and SSE routes are present in OpenAPI; `storyforge3 serve` startup was smoke-tested.
- Active provider validation passed for `Codex 直连中转` / `gpt-5.5`.
- Full production pipeline passes against `Codex 直连中转`: plan -> draft(chunked) -> normalize -> audit -> revise(patch) -> truth_extract -> export.
- Phase 2 stability fixes are validated: dedicated `plan-v1` avoids compose prompt misuse, recommender no longer upgrades local blocking rules to full rework, patch revise handles spot/surgical revisions in short requests, `truth-extract-v2` declares the required JSON schema, and `golden_three_hook` uses multi-dimensional hook detection plus explicit patch guidance.
- Latest 3-chapter E2E run: `books/e2e-multi-20260608-180847`, `success=True`, `3/3 exported`, `failed_chapters=0`, and cross-chapter truth retrieval passed.
- E2E chapter details: chapter 1 = 2255 chars, audit passed, 1 patch revision, 45 truth entries; chapter 2 = 2706 chars, audit passed, 0 revisions, 74 truth entries; chapter 3 = 2940 chars, audit passed, 0 revisions, 52 truth entries.
- Long-generation resilience uses 2s/4s/8s retry backoff, extra jitter for 504, 5 total attempts for 502/503/504, and 300s draft/revise timeout.

## Known Issues

- Relay provider latency is highly variable. Some calls can take several minutes, especially `draft_chunk_plan`, because of upstream waiting and retry/backoff.
- Full-text `rework` remains a rare long-generation path for severe cases such as `empty_text`; it can still hit provider limits. Current recommender logic keeps local blocking issues on patch revise instead.

## Contribution Guidelines

Run `pytest` and `ruff check .` before claiming completion. Do not add real secrets. Treat failed LLM calls as failed production evidence, not as successful fallback output.
