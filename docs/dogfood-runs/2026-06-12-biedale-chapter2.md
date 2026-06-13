# Dogfood Round 1: 《别打了》第 2–3 章（agent 模式全管线）

> 首次真实 dogfood。验证引擎核心价值 + 暴露阻断续写的根因。
> 本轮跨越两次运行：第 2 章（truth 超时失败）→ 定位根因 → 调高超时 → 第 3 章（全链路成功）。

## 基本信息

| 项目 | 内容 |
|------|------|
| 测试日期 | 2026-06-13 |
| 测试者 | 用户 + PM（Claude Code）+ Codex |
| 书籍 | 别打了，我帮你们翻译还不行吗? |
| 章节 | 第 2 章（续写，truth 失败）+ 第 3 章（续写，exported） |
| Provider / Model | weShareAi（relay）/ gpt-5.5 |
| 触发方式 | agent curl `POST /api/books/{id}/chapters/{n}/run`（全管线，非前端单步） |
| 后端 / 前端版本 | 275af86（HEAD）。超时通过环境变量覆盖，**无代码改动** |
| 超时配置 | `STORYFORGE3_LLM_TIMEOUT_SECONDS=600` + `STORYFORGE3_LLM_DRAFT_TIMEOUT_SECONDS=600` |

## 前置数据

| 项目 | 值 |
|------|-----|
| 第 1 章字数 | 1581（API status 实际值） |
| 第 1 章 truth 条目 | 29（11 facts + 4 char + 4 rel + 5 hooks + 4 irreversible）|
| 第 2 章 truth 条目 | **0（提取失败，见下）** |
| 世界观 rules | 9 条 |
| 核心角色 | 4 人（沈听澜 / 赫鲁 / 伊芙蕾 / 秦缝）|

## 时间记录（精确，来源 pipeline.jsonl）

### 第 2 章 — truth 超时失败

| 步骤 | 耗时 | 结果 |
|------|------|------|
| plan | 47.5s | ✅ gpt-5.5，1686→2078 tokens |
| draft（chunked） | 198.4s | ✅ draft_chunk 26s + length_normalize 55.7s |
| audit | 6ms | ✅ 机械，passed / 0 blocking / 3 warnings |
| truth_extract | 120s | ❌ **`provider request timed out`** |
| 全管线 | 423s（7分03秒）| ❌ failure（truth 挂） |

### 第 3 章 — 全链路成功（超时提到 600s 后）

| 步骤 | 耗时 | LLM 调用明细 |
|------|------|------|
| plan | 36.1s | 1686→1549 tokens |
| draft_chunk | 18.9s | 15202→719 tokens |
| length_normalize | 54.2s | 7534→2790 tokens |
| audit | 0s | 机械，0 blocking / 3 warnings |
| **truth_extract** | **402.5s（6分42秒）** | `in/out=None`（relay hold 不返回 usage），success |
| approve / export | 0s / 0s | human_confirm 自动通过 |
| **全管线 wall-clock** | **758.6s（12分39秒）** | ✅ **exported，2308 字** |

## 核心发现

### 发现 1 ⭐ truth_extract 超时根因彻底坐实

truth_extract 在 weShareAi relay 上**实测耗时 402.5s**。原 `default_timeout=120s` 必然超时（第 2 章失败原因），即使提到 300s 也悬。**结论：`default_timeout` 必须设到 ≥600s，不是可选项**——这是续写链路能否闭环的命门。用户观察"token 不消耗"= relay 把请求 hold 住 ~7 分钟才一次性返回（`in/out=None`，不流式），SF3 侧表现为静默等待，易误判为卡死。

### 发现 2 ⚠️ LLM 4 维审计未触发

audit 步骤 0s、纯机械（36 规则），`llm_calls` 中**无 auditor 调用**。CLAUDE.md 定义"4 LLM 维度：OOC / 战力一致 / 信息边界 / 情节逻辑"，但本轮未跑。需确认：是"机械审计通过即跳过 LLM 审计"的设计，还是 bug。若是 bug，质量闭环缺一环。

### 发现 3 ⚠️ truth 链路断裂影响续写

第 2 章 truth 提取失败 → 第 3 章 draft 时 `previous_truth` **只有第 1 章 29 条**。第 3 章能衔接第 2 章情节（巡夜队→秤房→活物），靠的是 `previous_chapter_tail`（1800 字文本），**非结构化 truth**。长篇会因 truth 缺失累积设定漂移。draft context_sources 实测：`truth_retrieval 1376 chars / 917 tokens`（仅第 1 章）。

### 发现 4 truth 步骤在 jsonl 无独立记录行

truth_extract 的耗时只能在 `full_pipeline` 行的 `llm_calls` 里找到，**无独立 `task=truth` 记录**（其他步都有）。可观测性 gap：单独看 truth 耗时要靠减法推算。建议 workflow 给 truth 步骤补独立 `_log_run`。

## 规划步骤详细观察（前端单步 plan，第 2 章）

- 后端 `POST /chapters/2/plan` 返回 `ok: true`，含 `goal` + `outline_node`
- 前端"完成" toast 弹出
- **但 plan 内容不在前端渲染**（Codex 已修：`lastPlan` state + 本章规划面板，72 passed）
- `ChapterService.plan()` 原本无状态：不持久化、不推进状态、不创建章节文件
- plan 后 `GET /chapters/2/status` 曾返回 `CHAPTER_NOT_FOUND`
- **结论**：单步 plan 与全管线不自洽（详见"设计审查"）

## 进度 UI 观察

| 项目 | 观察 |
|------|------|
| draft 期间进度条是否显示 | ⚠️ 本轮走 agent curl，SSE 进度对 background-triggered run 的前端可见性**未验证**（PipelineProgress 受 local isBusy 门控，见 PLAN.md 备注） |
| 进度条内容 | N/A（本轮未看前端） |
| 错误或超时展示 | 第 2 章 truth 超时返回 `status=needs_review` + `error=truth_extraction_failed`，前端能否展示未验 |

### 预填基线

- `storyforge3 health`：通过
- `pytest --tb=no -q`：501 passed
- `pnpm test`：71 passed
- `pnpm build`：通过（仅既有 CodeMirror chunk 警告）
- API 数据读取已验证：book / chapter / truth / world / characters 均可读取

## Truth 召回观察

| 项目 | 观察 |
|------|------|
| 第 3 章 draft 是否含前序 truth | ✅ 含 `truth_retrieval`（1376 chars / 917 tokens），**但仅第 1 章** |
| 召回了哪些关键事实 | 第 1 章：角色身份/关系/钩子（具体条目未逐条核）|
| 召回对第 3 章是否有帮助 | 部分——角色身份延续有效；第 2 章新增设定（巡夜队/眠息草/木匣活物）**未结构化召回** |
| 遗漏 | 第 2 章 truth 整章缺失（truth 提取失败所致），靠 `previous_chapter_tail` 文本兜底 |

## 章节质量评估

| 维度 | 第2章(1-5) | 第3章(1-5) | 备注 |
|------|:---:|:---:|------|
| 设定一致性（12 文明体系） | 5 | 5 | 夜灯仓/旧仓语/秤房验末三方同签/眠息草，跨章连贯 |
| 角色区分度 | 5 | 5 | 赫鲁(兽人獠牙斧) / 伊芙蕾(精灵银针冷) / 秦缝(账房笑面刀) / 沈听澜(吐槽翻译者)，各立得住 |
| 情节推进 | 4 | 4 | 第2章灭口→查仓→抢匣；第3章推进秦缝内鬼线+秤房陷阱，节奏略密 |
| 翻译机制（核心卖点） | 5 | 5 | 第3章翻译能力直接左右生死（"先砍翻译的舌头"、墙用旧仓语念"三方已到可以开封"、译者可代签）|
| 文风质量 | 4 | 5 | 第3章增网文幽默感（"职业规划从装死群众升级成背锅货工""那我努力涨价"）|
| 字数达标（2000-3000） | ✅ 2226 | ✅ 2308 | 均达标 |

**质量结论**：核心价值确认——引擎能写出匹配十二文明世界观、翻译机制驱动情节、有网文爽感的好章节。

## 审计质量

| 项目 | 观察 |
|------|------|
| 机械审计结果 | 第2/3章均 0 blocking / 3 warnings（warnings 具体规则未逐条核）|
| 命中是否合理 | 0 blocking 说明机械层无硬伤 |
| LLM 审计 4 维度 | ⚠️ **未触发**（见发现 2）|
| 是否漏判 | 无法判定（LLM 审计未跑）|

## 修订质量

本轮 audit 均 0 blocking，**未触发 revise**。recommender 未被调用。修订模式 / 效果本轮无数据。

## 问题列表

| # | 严重度 | 问题描述 | 复现步骤 | 状态 |
|---|--------|---------|---------|------|
| 1 | P1 | Plan 结果不在前端展示 | 点"规划"→ toast 完成但无内容 | ✅ Codex 已修（lastPlan + 本章规划面板，72 passed）|
| 2 | P2 | 不存在章节(2-5)产生 404 控制台噪音 | 打开有 1 章的书 → ChapterList 预创建 5 卡 | ✅ Codex 已修（useChapterStatus 拦截 404）。注：浏览器仍打 HTTP 404 红字 |
| 3 | P1 | Plan 后端不持久化 + 状态不推进 | plan 后 checkmark 不亮、刷新后内容消失 | ⛔ 设计级缺陷，指令 `directive-10a-dogfood-fix1-plan-persistence.md`（PLAN.md 已完整含 6 项，待放行 Codex）|
| 4 | **P0** | truth_extract 超时（120s 远不够） | relay 上 truth 实测 402.5s | ⚠️ **根因坐实**：本轮用 env 覆盖 600s 跑通，但**代码层 default 仍 120s，必须正式修**（提 default≥600 或 truth 走长超时）|
| 5 | P2 | book_id 被用作页面标题 | 标签/控制台显示 `别打了w...20260611` | 🔲 待修 |
| 6 | **P1** | LLM 4 维审计未触发 | audit 步骤 0s、无 auditor 调用 | ⚠️ **新发现**，需查设计 vs bug。若 bug，质量闭环缺一环 |
| 7 | P1 | truth 链路断裂影响续写 | 第2章truth失败→第3章只召回第1章truth | ⚠️ 修 #4 后需补回第2章truth，验证多章结构化召回 |
| 8 | P3 | truth 步骤 jsonl 无独立行 | 看 truth 耗时要靠减法推算 | 🔲 可观测性 gap，workflow 补独立 `_log_run` |

## 设计审查：Plan 步骤不自洽（问题 #3 深挖）

PM 代码审查确认问题 #3 是**设计级缺陷**，非简单 bug：

**核心矛盾**：`ChapterService.plan()` 完全无状态，但 UI 和全管线都把它当持久化步骤。

| 层 | 对 plan 的处理 | 是否持久化 |
|----|--------------|-----------|
| 全管线 `ChapterWorkflow.run()` | 推进状态 PLANNED + step_plan | ✅ |
| 单步 `POST /chapters/{n}/plan` | 仅返回 ChapterIntent 内存对象 | ❌ |
| 前端 ChapterPipeline | 渲染 lastPlan，checkmark 基于 result.status | 依赖后端 |

**三个缺失**：① `StoragePaths` 无 `plan_file()`；② `plan()` 无状态推进；③ `get_status()` 无文本即返回 None → 404。

**修复方向**：Plan 升级为持久化一等步骤，与全管线自洽。详见 `directive-10a-dogfood-fix1-plan-persistence.md`。豆包独立审查（`chapter-plan-persistence-review.md` + `豆包评估.md`）结论一致，并补强前端恢复 + 语义澄清。

## 总体判定

- [x] **可继续使用**（第 3 章 exported，核心价值确认）
- [ ] 需修复后再用
- [ ] 阻断

**前提**：truth 超时（#4）必须正式修，否则续写链路每次在 truth 断裂。

## 是否继续写下一章

**是，已继续并成功**。第 2 章 →（修超时）→ 第 3 章 exported。建议修 #4 + #6 后再写第 4 章，并验证 3 章完整 truth 召回。

## 对 Phase 10B（AutoDirector）的输入

1. **超时是第一道坎**：自动导演连续跑多章，truth_extract 每章 ~7 分钟，N 章 = N×7 分钟纯 truth 等待。必须支持 checkpoint/resume，单章 truth 超时不能让整批失败（当前 truth 失败 → needs_review，章节文本已存，可重试 truth）。
2. **truth 链路必须自愈**：自动导演要能检测"某章 truth 缺失"并补提，否则长篇累积漂移。
3. **LLM 审计需确认是否在管线内**：若设计上机械通过就跳过，自动导演对质量门禁的信心要打折。
4. **可观测性**：每步独立 jsonl 行 + 累积 llm_calls，AutoDirector 的进度展示可直接消费 pipeline.jsonl。
