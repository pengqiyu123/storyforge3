# 批量提交指令（2026-06-13，下发 Codex）

> 范围：把本会话产出的三块工作（火山路由 fix / CI 修复 / CCSwitch 供应商组件）按 **3 个 conventional commit** 提交并推送。PM 已完成全部实现 + 验证（见下），Codex 只需按此分组提交、回推门禁即可。
>
> HEAD：`ad07b27 fix(chapter): persist plan intent and advance status to PLANNED (dogfood #1)`。`96d2975`(truth timeout) 与 `ad07b27`(plan persistence) **已提交**，勿重复。

---

## 当前 git 状态（PM 核实）

- **已 staged**：`.github/workflows/ci.yml`、`.gitignore`、`web/src/components/books/{BookCard,BookList,CreateBookDialog}{.tsx,.test.tsx}`（5 文件）
- **unstaged modified**：`CLAUDE.md`、`docs/quickstart.md`、`src/storyforge3/api/deps.py`、`src/storyforge3/api/routes/providers.py`、`src/storyforge3/llm/{ccswitch_db_reader,llm_service,provider_config}.py`、`tests/api/test_providers.py`、`tests/test_{ccswitch_db_reader,llm_service,provider_config}.py`、`web/src/api/client.ts`、`web/src/hooks/useHealth.ts`、`web/src/pages/{DashboardPage,SettingsPage}.tsx`
- **untracked**：`web/src/api/providers.ts`、`web/src/hooks/useProviders.ts`、`web/src/components/providers/{ProviderPanel,ProviderCard,CCImportDialog,HealthBadge}{.tsx,.test.tsx}`（4 组件 + 4 测试）；以及 4 个 PM 文档（见提交 4）
- ⚠️ **`books/别打了…/book.json` 是 modified——严禁纳入本次任何提交**（运行时 dogfood 数据，非代码）

> LF/CRLF 警告是 Windows 换行符提示，**不要**为此在本批提交里改 `.gitattributes`。

---

## 提交 1 — `fix(llm): preserve Volcano /api/coding path prefix in route builder`

**根因**：`COMPAT_SUFFIXES` 把 `/api/coding`、`/coding` 当可剥兼容后缀，但火山引擎 Coding Plan 的 `/api/coding` 是真实路径前缀（正确端点 `…/api/coding/v1/messages`），剥掉后变 `…/v1/messages` → 404。DB 里无任何 provider 需要剥这两项。

**文件**：
- `src/storyforge3/llm/llm_service.py`（COMPAT_SUFFIXES 移除 `/api/coding`、`/coding` + 注释）
- `tests/test_llm_service.py`（夹具默认候选从 `/api/coding` 改中性 base；`build_endpoint_url` 断言改为「`/api/coding` 保留」）

**body 要点**：移除两项后端点正确解析为 `/api/coding/v1/messages`；全量 522 绿。

---

## 提交 2 — `fix(ci): anchor books/ ignore, ship un-ignored components, invoke pytest via module`

**根因（CI 三连失败，全是预存基础设施债，非回归）**：
1. `.gitignore:17 books/` 未锚根 → 误伤 `web/src/components/books/` → 5 个组件从未入库 → CI checkout 找不到 `CreateBookDialog`（frontend job fail）
2. CI 跑裸 `pytest tests/` → `No module named 'tests'`（`tests/conftest.py` 声明 `pytest_plugins=("tests.conftest_api",)`，需 cwd 在仓库根用 `python -m pytest`；backend job fail）
3. desktop Tauri build.rs（本次不处理，留待后续）

**文件**：
- `.gitignore`（`books/` → `/books/`，仅忽略根级数据目录）
- `.github/workflows/ci.yml`（backend Test 步骤 `pytest tests/ -q` → `python -m pytest tests/ -q`）
- `web/src/components/books/{BookCard,BookList,CreateBookDialog}{.tsx,.test.tsx}`（此前被错误忽略的源文件，现已 un-ignore，纳入版本）

---

## 提交 3 — `feat(providers): CCSwitch provider-switching panel (web UI + REST endpoints)`

**功能**：`/settings` → 「AI 供应商」面板：导入（从 CC-Switch SQLite DB，只读）/ 切换 active / 验证健康 / 移除；后端补 6 个端点；预留手动模式（per-task 模型路由）数据结构 + `GET /routing`（可用）+ `PUT /routing`（501 stub，等 config 持久化）。所有输出脱敏 api_key。

**后端文件**：
- `src/storyforge3/llm/ccswitch_db_reader.py`（输出加 `has_api_key`/`cc_is_current`/`cc_category`；加 `is_db_available()`）
- `src/storyforge3/llm/provider_config.py`（`verify_provider` 改 **async**——修在 async 路由里 `asyncio.run` 会炸的隐患；新增 `remove_provider` + `is_db_available()`；删去随之未用的 `import asyncio`）
- `src/storyforge3/api/routes/providers.py`（Pydantic 模型 + 6 端点：`GET /available`、`POST /import`、`PUT /active`、`POST/{key}/verify`、`DELETE/{key}`、`GET/PUT /routing`）
- `src/storyforge3/api/deps.py`（新增 `get_provider_manager` 依赖——测试可注入 FakeReader/FakeLLMService，否则路由会读真 DB / 发真 LLM 请求）
- `tests/api/test_providers.py`（+12 端点测试，含可用/导入/切换/验证/移除/路由，依赖覆盖 + autouse 清理）
- `tests/test_provider_config.py`（+4：remove 三态 + is_db_available 委托；verify 2 例改 async/await）
- `tests/test_ccswitch_db_reader.py`（claude 解析期望 dict 补 `has_api_key`/`cc_is_current`/`cc_category`）

**前端文件**：
- `web/src/api/client.ts`（`api` 加 `delete` 方法）
- `web/src/api/providers.ts`（新；类型 + `providersApi`，镜像后端模型）
- `web/src/hooks/useProviders.ts`（新；7 个 TanStack Query hook，接管 `["providers"]` query key）
- `web/src/hooks/useHealth.ts`（`useProviders` 改为从 `useProviders.ts` re-export 别名，消除双缓存）
- `web/src/pages/DashboardPage.tsx`（`Provider` 类型 → `ImportedProvider`）
- `web/src/pages/SettingsPage.tsx`（插入 `<ProviderPanel/>`）
- `web/src/components/providers/{ProviderPanel,ProviderCard,CCImportDialog,HealthBadge}.tsx` + 4 个 `.test.tsx`（全新）

**文档**：`CLAUDE.md`（Current Validation 加一行）、`docs/quickstart.md`（§2.1 改写为 Web UI 流程 + CLI/API + 手动模式 routing 501 说明）

---

## 提交 4（可选）— `docs: add PM directives and audit for dogfood fix1`

4 个 untracked PM 文档，与本批代码无强耦合，可单独 docs 提交或保留 untracked（用户定）：
- `docs/reviews/codex-execution-plan-audit.md`（豆包审计 + PM §11 收口指令，已被 ad07b27 执行）
- `docs/reviews/chapter-plan-persistence.md`
- `docs/directives/directive-10a-dogfood-fix1-plan-persistence.md`
- `docs/reviews/doubao-phase10a-direction-eval.md`

---

## 提交纪律（红线）

- ❌ **不 `git add books/`**（运行时 dogfood 数据）；提交 3 用**显式路径列表** add，不用 `git add -A`/`git add .`
- ❌ 不改 `.gitattributes`（CRLF 警告无害）
- ❌ 不重提 `96d2975`/`ad07b27`
- ✅ 每个 commit 后跑对应门禁（见下），全绿再 push

## 验收门禁（push 前必须全过；从 storyforge3 目录跑）

```powershell
cd D:\python\Novel\storyforge3
.\.venv\Scripts\python.exe -m pytest --tb=no -q      # 522 passed
.\.venv\Scripts\python.exe -m ruff check .            # clean
cd web
pnpm test --run                                       # 85 passed
pnpm build                                            # clean（CodeMirror 大块警告为既有，忽略）
```

## 回报

- 4 个 commit hash
- 4 项门禁结果
- push 后 `origin/main` HEAD

> 注：后端已在 :8000 跑最新代码（含新端点）；前端 :5173 刷新后 `/settings` 即见面板。提交不影响运行中进程。
