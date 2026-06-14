# CLAUDE.md

## Project Overview

StoryForge3 is a Chinese web-novel full-workflow creation engine. It supports creating a book from a blank page, building world and character context, planning volumes, and producing single or multi-chapter runs through audit, revision, truth extraction, and export.

## Product Direction — agent-mode ONLY (manual mode deferred)

> **Decision (2026-06-14, owner-confirmed).** This is recorded here to prevent drift.

StoryForge3 ships **agent-mode only**. The product model is:

- **The agent (Claude Code / Codex) or external API drives the pipeline** — plan / draft / audit / revise / truth / export are triggered by the agent calling the REST API, not by the user clicking buttons.
- **The Web UI is a read-only viewer** ("Run Viewer + 结果查看器"): it shows run progress (SSE) and stage results. The chapter page's stage steps are **view tabs** — clicking switches to that stage's result; the checkmark = "this stage has produced output". **Stage steps are NOT run triggers.**
- **No run buttons in the UI.** Do not re-add click-to-run step buttons (规划/起草/审计/修订/批准/导出) or a "运行全流程" manual trigger without an explicit owner decision. Running is agent/API only.
- **Manual text editing stays** (the author can edit chapter prose by hand) — that is refinement, not pipeline execution, and is not "manual mode".

**Why:** the project pivoted to agent-mode-first; a button-driven UI assumes the user is a manual operator, which conflicts with the agent-driven model and produced inconsistent UX (run-on-click, re-triggering completed steps, progress not showing for agent runs).

**Implication for contributors:** when working on the chapter page, treat it as a viewer. New "run" affordances belong behind the API + agent, not in the UI. Full per-stage result persistence (so every view tab is always loadable) and the complete `allowedActions` gating are P1 — see `docs/architecture/run-state-and-viewer.md`.

## Commands

```powershell
cd D:\python\Novel\storyforge3
& .\.venv\Scripts\python.exe -m pytest
& .\.venv\Scripts\python.exe scripts\e2e_test.py
& .\.venv\Scripts\python.exe scripts\e2e_multi_chapter.py
storyforge3 health
storyforge3 serve --port 8000
ruff check .
cd web; pnpm build; pnpm test
cd ..\src-tauri; cargo test; cargo clippy -- -D warnings; cargo fmt --check; cargo build
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

- Provider: `weShareAi`
- Base URL: `https://weshareai.xyz`
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
FastAPI exposes these services through REST routes plus `/api/events` SSE, and `storyforge3 serve --port 8000` starts the local API server.

### Desktop Shell

Phase 6D-1 adds a thin Tauri 2 desktop shell under `src-tauri/`. Rust only manages the Python FastAPI child process, health-check polling, desktop window lifecycle, tray menu, window state, and single-instance behavior. The React frontend still uses HTTP/SSE; in Tauri mode it targets `http://127.0.0.1:8000` instead of relying on Vite's `/api` proxy.

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

Current status, history, and forward plan are split across `docs/current.md`, `docs/history.md`, and `docs/next.md`. Architecture decisions are recorded under `docs/adr/`.

- Backend unit/API baseline: 501 passed with 91% coverage in the Phase 10A-1/10A-2 coverage run; `ruff check .` clean.
- Frontend baseline: 71 passed, `pnpm build` clean except the existing large CodeMirror chunk warning.
- Rust desktop baseline: 5 passed (4 prior + 1 sidecar candidates from 8A-1). `cargo fmt --check`, `cargo clippy -- -D warnings`, and `cargo build` clean. Current environment has no `cargo`, so Rust was not rerun in 8A-1 verification.
- FastAPI Phase 1 is complete: health, books, world, characters, volumes, chapters, truth, export, providers, daemon, and SSE routes are present in OpenAPI; `storyforge3 serve` startup was smoke-tested.
- Active provider validation passed for `weShareAi` / `gpt-5.5`.
- Full production pipeline passes against `Codex 直连中转`: plan -> draft(chunked) -> normalize -> audit -> revise(patch) -> truth_extract -> export.
- Phase 2 stability fixes are validated: dedicated `plan-v1` avoids compose prompt misuse, recommender no longer upgrades local blocking rules to full rework, patch revise handles spot/surgical revisions in short requests, `truth-extract-v2` declares the required JSON schema, and `golden_three_hook` uses multi-dimensional hook detection plus explicit patch guidance.
- Latest 3-chapter E2E run: `books/e2e-multi-20260608-180847`, `success=True`, `3/3 exported`, `failed_chapters=0`, and cross-chapter truth retrieval passed.
- E2E chapter details: chapter 1 = 2255 chars, audit passed, 1 patch revision, 45 truth entries; chapter 2 = 2706 chars, audit passed, 0 revisions, 74 truth entries; chapter 3 = 2940 chars, audit passed, 0 revisions, 52 truth entries.
- Long-generation resilience uses 2s/4s/8s retry backoff, extra jitter for 504, 5 total attempts for 502/503/504, and 300s draft/revise timeout.
- Phase 4 complete: atomic writes (`storage.py` temp+rename), failure diagnostics (`_persist_diagnostics`), context source tracking (`ContextBlock`/`ContextPackage` with priority-based budget trimming), API integration tests (15 endpoints).
- Phase 5A complete (Frontend MVP): React 19 + Vite 7 + TypeScript + Tailwind 4 + shadcn/ui, ~59 source files, 14 frontend tests. Book CRUD, Chapter Pipeline UI, Dashboard, SSE events, FocusMode.
- Phase 5B skipped per user instruction.
- Phase 5C complete (Infrastructure): PipelineLogger JSONL audit logging (7 hooks), 11/11 Service Protocol implementations (AuditService, TruthService, PromptService, StyleService added), export pre-snapshots (zip + meta.json + auto cleanup).
- Phase 6A-1 complete: CodeMirror chapter editor with Chinese character count and read-only/edit modes.
- Phase 6D-1 complete: Tauri scaffold, Python process manager, tray menu, local API health wait, desktop API/SSE URL resolution, and `serve --port` local binding.
- Phase 7A-1 complete: manual chapter editing with SHA-256 optimistic locking, `PUT /text`, dirty-state UI, Ctrl+S save, and `NEEDS_REVIEW` transition after manual edits.
- Phase 7A-2 complete: paragraph-level audit issue locations, `AuditResponse.rule_results`, clickable audit rows, snippet display, CodeMirror highlights, and scroll-to-issue in the chapter pipeline.
- Phase 7A-3 complete: real chapter revise now reuses workflow patch/rework logic, revise/update save `.before.md` snapshots, `revision_diff` is returned in chapter responses, and the web chapter pipeline shows a paragraph-level before/after diff panel after revise.
- Phase 7B-1 complete: `TruthStore.load_history()` + `GET /truth/history` endpoint; `TruthPanel` component with chapter-grouped 6-category display, irreversible-facts highlighting, chapter tabs, and search filter; "真相" tab added to BookDetailPage.
- Phase 7B-2 complete: `SnapshotManager.restore_snapshot()` with whitelist (chapters/ + state/) and zip slip protection; `GET /snapshots` + `POST /restore` API; `SnapshotPanel` component (ported from CC-Switch BackupListSection) with confirm dialog; "快照" tab added to BookDetailPage.
- Phase 7B-3 complete: `GET /export-preview?fmt=` endpoint with 3 formats (tomato_txt/markdown/qidian_txt), pure in-memory formatting; `ExportPreviewDialog` component with format selector, readonly preview, format errors display, copy-to-clipboard, and export download.
- Phase 7C complete: MCP error recovery suggestions on 4 ValueError positions, `next_step` output fields on `ChapterStatusInfo`/`AuditSummary`/`ShortStoryStatusInfo`, structured `DraftResult` model for `draft_chapter`, `_suggest_next_step()`/`_suggest_short_story_next_step()` state-to-suggestion mappings, 15 tool docstrings with operation type tags (`[只读]`/`[创建]`/`[LLM 调用]`/`[修改]`), `MCP_INSTRUCTIONS` constant with long-form/short-form workflow descriptions, `docs/architecture/mcp-registration.md` with `claude mcp add` command, settings.json snippet, 15-tool reference table, and troubleshooting. Directives: `docs/directives/directive-7c-1.md` and `docs/directives/directive-7c-2.md`.
- Phase 7D complete: GitHub Actions CI/CD (`ci.yml` backend/frontend/desktop jobs, `release.yml` Windows tag release + updater artifact verification), Tauri updater artifact config (`createUpdaterArtifacts` + pubkey placeholder), `docs/release/release-setup.md` signing guide, and user data management (`WorkspaceService`, `/api/workspace/validate|backup|restore`, `/settings` workspace UI with validate/backup/restore). Directives: `docs/directives/directive-7d-1.md` and `docs/directives/directive-7d-2.md`.
- Phase 8A-1 complete: PyInstaller sidecar packaging (`scripts/desktop_entry.py`, `storyforge3-api.spec`, `build_sidecar.ps1`), Tauri integration (`tauri-plugin-shell`, `externalBin`, `shell:allow-spawn`), process_manager.rs refactored to sidecar-first/venv-fallback dual mode.
- Phase 8B-1 complete: Service test gap closure (PromptService 7 tests, StyleService 7 tests, TruthService 6 tests). Service layer 17/17 test coverage.
- Phase 8 progress: 2/2 sub-phases (8A-1 ✅, 8B-1 ✅).
- Phase 8.5 complete: Dogfood RC user-facing docs (`README.md`, `docs/quickstart.md`, `docs/dogfood-protocol.md`), release setup sidecar/venv wording updated, cold-start smoke passed (temp venv install/import/CLI help, `storyforge3 serve`, `/api/health`, create-book API, Vite proxy). Active provider is `weShareAi / gpt-5.5` and `storyforge3 health` passes. Real write-a-chapter dogfood is documented but not executed yet. Directive: `docs/directives/directive-8-5.md`.
- Phase 10A complete: 10A-1 complete (`docs/current.md`, `docs/history.md`, `docs/next.md`, 5 ADRs, 91% coverage baseline); 10A-2 complete (`generate_text_stream()` for openai_chat/openai_responses, `ChunkedGenerator` on_progress callback, SSE `llm:progress`, truth-before-export guard); 10A-3 complete (frontend `PipelineProgress` component, `ChapterPipeline` SSE integration, progress-event toast suppression, frontend tests 62 -> 71). Dogfood preparation is now active: `storyforge3 health` currently passes against `weShareAi / gpt-5.5`, backend is 501 passed, frontend is 71 passed, and Round 1 / Round 2 run templates live under `docs/dogfood-runs/`. Directives: `docs/directives/directive-10a-1.md`, `directive-10a-2.md`, `directive-10a-3.md`, `directive-dogfood-prep.md`.
- CCSwitch provider panel complete: Web UI at `/settings` → **AI 供应商** for import / switch-active / verify / remove, backed by new REST endpoints (`GET /api/providers/available`, `POST /import`, `PUT /active`, `POST/{key}/verify`, `DELETE/{key}`) + reserved manual-mode `GET/PUT /api/providers/routing` (PUT is a 501 stub). `ProviderConfigManager.verify_provider` is now async; added `remove_provider` + `is_db_available`. Frontend: `api/providers.ts`, `hooks/useProviders.ts`, `components/providers/{ProviderPanel,ProviderCard,CCImportDialog,HealthBadge}.tsx`.

## Known Issues

- Relay provider latency is highly variable. Some calls can take several minutes, especially `draft_chunk_plan`, because of upstream waiting and retry/backoff.
- Full-text `rework` remains a rare long-generation path for severe cases such as `empty_text`; it can still hit provider limits. Current recommender logic keeps local blocking issues on patch revise instead.

## Contribution Guidelines

Run `pytest` and `ruff check .` before claiming completion. Do not add real secrets. Treat failed LLM calls as failed production evidence, not as successful fallback output.
