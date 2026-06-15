# 指令 P1-3：门禁统一（allowedActions 纯函数 + 后端 guard + 前端只读镜像）

> 下发 Codex。前置：P1-1（RunRecord）/ P1-1b（reconcile）/ P1-2（Run Viewer）/ P-IMP-3b（validity）均 ✅。
> 依据：架构 spec [`docs/architecture/run-state-and-viewer.md`](../architecture/run-state-and-viewer.md) §6 + §8 文件地图 P1 收尾项。

> ⚠ **范围调整（2026-06-15 方向纠偏，见 [`pm-direction-correction-2026-06-15.md`](../reviews/pm-direction-correction-2026-06-15.md)）**
> 1. **P1-3 是引擎收尾的最后一项**——完成后立即转真实多章生产（《别打了》从干净 ch2 续写 ch3）。**勿扩展范围、勿顺手加新引擎特性。**
> 2. **前端 `gating.ts` 只读镜像 → DEFER（移出本指令）**。agent-mode 下前端无运行按钮，"下一可执行阶段"信息无承载处；guard 的 409 错误体已自带 `current_status/required` 诊断。本指令**只做后端** `allowed_actions()` + guard。
> 3. ch3/4 幽灵已 discard（PM 已执行，干净 ch2 状态），本指令不涉及 heal。

## 背景

当前门禁**分散**：状态机 `state/machine.py` 管合法转移、`ExportService` guard `TRUTH_COMMITTED`、各 service 内零散校验（如 approve 需 audit.blocking==0）。问题：
- 无单一真相源——加新阶段/新约束要改多处，易漏。
- 前端无法回答"这章下一步能做什么"（agent-mode 下虽无按钮，但 Run Viewer 应能只读告知可执行阶段，帮用户理解状态）。
- agent/API 调用缺少集中防御——靠各 service 自觉校验。

P1-3 引入**一个纯函数** `allowed_actions()` 作门禁唯一真相源，后端 guard 强制、前端只读镜像。

## 任务

### 1. `allowed_actions()` 纯函数（新 `src/storyforge3/state/gating.py`）

```python
def allowed_actions(
    chapter_status: ChapterStatus,
    run_status: RunStatus | None,
    audit_blocking: int,
    truth_exists: bool,
) -> frozenset[str]:
    """门禁唯一真相源。返回允许的 stage action 集合（plan/draft/audit/revise/approve/truth/export）。"""
```

规则（移植 spec §6 表，agent-mode 下 governs agent/API 调用，不限用户）：

| chapter_status | run_status | 允许动作 |
|---|---|---|
| 任意 | RUNNING/WAITING_FOR_HUMAN | `{}`（运行中全禁，仅 cancel 在 run 层） |
| EMPTY | idle | `{plan}` |
| PLANNED | idle | `{draft, plan}` |
| DRAFTED | idle | `{audit}` |
| AUDITED(blocking=0) | idle | `{approve, revise}` |
| AUDITED(blocking>0) | idle | `{revise}`（强制） |
| REVISED | idle | `{audit}`（重审） |
| APPROVED | idle | `{truth}` |
| TRUTH_COMMITTED | idle | `{export}` |
| EXPORTED | idle | `{}`（新版本规划是显式版本化，**本指令 Out of Scope**） |
| NEEDS_REVIEW | idle | `{}`（由用户/agent 选恢复点，独立处理） |

强制门禁（guard 必查）：
- `approve` 需 `audit_blocking==0`
- `truth` 需 `chapter_status==APPROVED`
- `export` 需 `chapter_status==TRUTH_COMMITTED`（或 APPROVED 且 truth_exists，兼容既有）

### 2. 后端 guard（集中接入）

`api/routes/chapters.py` 的 plan/draft/audit/revise/approve/truth/export 执行入口：调 `allowed_actions()` 校验当前状态，不允许则抛 `ApiError(409, code="ACTION_NOT_ALLOWED", message=<中文原因 + 当前状态 + 缺什么>)`。

- 不重写各 service 的既有校验（保留作 defense-in-depth），但**入口层**统一走 `allowed_actions()`。
- 错误响应含 `current_status` / `required` 字段，便于 agent/前端诊断。

### 3. 前端只读镜像（`web/src/lib/gating.ts`）—— ⚠ DEFER，本指令不做

> 方向纠偏后移出范围。agent-mode 下前端无运行按钮，"下一可执行阶段"无承载处；guard 的 409 响应已含 `current_status/required` 诊断，足够。**本指令只交付后端 §1+§2。** 前端镜像待真实 dogfood 证明"用户需要看可执行阶段提示"才做（需求驱动）。

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| 门禁规则表 | `docs/architecture/run-state-and-viewer.md` §6 | **设计直接移植** |
| 状态枚举 + 合法转移 | `state/machine.py`（P1-1 已加 TRUTH_COMMITTED） | **直接复用** |
| ExportService guard | `services/export_service.py` TRUTH_COMMITTED 校验 | **保留 + 抽公共规则** |
| 错误响应模型 | `api/errors.py` `ApiError`（providers.py 已用 code 模式） | **模式复用** |

**新写比例**：约 **25%**（前端镜像 DEFER 后）。`gating.py` 纯函数（新）+ chapters.py 入口接入（薄包装）+ 测试。规则本身 spec 已定。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥566 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
pnpm --dir web typecheck                                 # clean
pnpm --dir web test                                      # 全绿
```

手动：
- 构造 chapter 各状态，`allowed_actions()` 返回与 §1 表一致（参数化测试覆盖每行）。
- approve 时 `audit_blocking>0` → API 返 409 `ACTION_NOT_ALLOWED`（含 current_status/required）。
- export 未到 TRUTH_COMMITTED → 409。

## 必须覆盖的测试

- `gating.py`：§1 表逐行参数化（含 RUNNING 全禁、blocking 分支、NEEDS_REVIEW）。
- chapters.py 入口：disallowed action → 409 + 正确 code/字段；allowed → 通过。

## 红线

- ❌ 不在 UI 加任何 action 按钮（agent-mode-only；前端只读镜像）。
- ❌ 不做 EXPORTED→新版本（版本化是独立设计，Out of Scope）。
- ❌ 不改各 service 既有业务校验（只加入口层 guard 作集中真相源）。
- ❌ 不改 `allowed_actions()` 语义去迁就现状 bug——若发现 service 行为与表冲突，按表为准并修 service（在回报里标出）。

## 回报

- commit hash（建议 `feat(gating): unified allowed_actions + backend guard + frontend mirror`）
- pytest + ruff + typecheck + 前端 test
- 一次 disallowed approve（blocking>0）的 409 响应体 + 一次前端「下一可执行阶段」只读显示 DOM

## Out of Scope

- ❌ **前端 `gating.ts` 只读镜像**（DEFER —— agent-mode 无按钮承载，409 错误体已诊断；待 dogfood 证明需要才做）。
- ❌ EXPORTED→新版本规划（需版本化设计，独立指令）。
- ❌ P-IMP-2 / P-IMP-4（独立指令，DEFER 至 dogfood 暴露需求）。
- ✅ **真实多章生产（《别打了》从干净 ch2 续写 ch3）= P1-3 验收后的首要动作**，非"建议"——见方向纠偏。本指令不覆盖，但 P1-3 完成即启动。
