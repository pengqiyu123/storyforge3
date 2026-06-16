# P-PROMPT-P0：提示词结构清理

> PM 指令 | 2026-06-16
> 优先级：P0（结构缺陷修复，不改提示词内容）
> 预计工时：1-2 天
> 前置：无
> 调研依据：`docs/research/prompt-optimization-research.md` §1.3-1.5 + `docs/research/prompt-optimization-plan.md` §二

---

## 问题陈述

SF3 提示词系统存在 4 个结构性缺陷：

1. **draft 双轨制**：`chapter_service.draft()` 用内联 `CHAPTER_DRAFT_PROMPT`，`workflow.step_draft()` 用注册表 `compose-v1`，同一章节走不同路径产出风格不一致
2. **length_normalize 双轨制**：注册表 `length-normalize-v1` 存在但未被使用，实际用内联 prompt
3. **孤儿模板**：`audit-v1`、`length-normalize-v1`、`truth-extract-v1` 三个模板注册了但无任何代码引用
4. **`_SafeDict` 静默失败**：`registry.py` 的 `render_system_prompt()` 使用 `_SafeDict`，未定义的占位符原样保留 `{xxx}` 发给模型而不报错

## 目标

1. 统一 draft 到注册表单一来源
2. 统一 length_normalize 到单一来源
3. 清理 3 个孤儿模板，消除维护负担
4. 修复占位符静默失败问题

**本指令不改任何提示词的具体文本内容**。内容升级在 P-PROMPT-P1 中实施。

## 改动范围

### P0-1：统一 draft 双轨制

**文件**：`src/storyforge3/services/chapter_service.py`

**改动**：
1. 删除内联 `CHAPTER_DRAFT_PROMPT` 常量（约 L34-43）
2. `draft()` 方法改为从注册表获取 compose 模板：
   - `template = registry.get_latest("compose")`
   - `system_prompt = render_system_prompt(template, chapter_no=chapter_no)`
3. 如果 `draft()` 的 payload 组装逻辑（style_prompt 拼接、同人模式上下文追加）与 `workflow.step_draft()` 有差异，保留这些差异但统一 system prompt 来源
4. 确保 `generate_text()` 调用的 task_name 不变（仍为 `chapter_draft` 或 writer 模型）

**注意事项**：
- 内联 `CHAPTER_DRAFT_PROMPT` 有 7 条写作约束（场景推进/对话辨识/动作替代情绪/禁内心独白词/禁总结词/场景切换/禁工程术语），而注册表 `compose-v1` 只有 5 条续写约束。**P0 阶段不合并内容**，只统一来源到注册表。如果这导致 draft 质量下降，在 P-PROMPT-P1 中通过 compose-v2 解决
- 需要验证 `draft()` 方法是否是实际被 API 调用的路径（确认 `run_full_pipeline` 走的是 workflow 还是 service）

### P0-2：统一 length_normalize 双轨制

**文件**：
- `src/storyforge3/prompts/registry.py`（删除 `length-normalize-v1`）
- `src/storyforge3/services/length_normalizer.py`（保持不变）

**改动**：
- 从 `create_default_registry()` 中删除 `length-normalize-v1` 的 `register(...)` 调用
- `LengthNormalizer._prompt()` 内联 prompt 保持不变（它是实际在用的）
- **不做**：不把内联 prompt 迁移到注册表（P0 只清理孤儿，不做迁移）

### P0-3：清理孤儿模板

**文件**：`src/storyforge3/prompts/registry.py`

**改动**：
从 `create_default_registry()` 中删除以下 3 个 `register(...)` 调用：
1. `audit-v1`（task_type="audit", version=1）— 未被任何代码引用，真正用的是 `AuditRunner` 纯规则 + `llm-audit-v1`
2. `length-normalize-v1`（task_type="length_normalize", version=1）— 合并到 P0-2
3. `truth-extract-v1`（task_type="truth_extract", version=1）— 已被 v2 取代

**清理后注册表应剩 7 个模板**：

| task_type | prompt_id | 版本 |
|---|---|---|
| compose | compose-v1 | 1 |
| plan | plan-v1 | 1 |
| truth_extract | truth-extract-v2 | 2 |
| revise | revise-v1 | 1 |
| llm_audit | llm-audit-v1 | 1 |
| short_plan | short-plan-v1 | 1 |
| short_draft | short-draft-v1 | 1 |

### P0-4：修复 `_SafeDict` 静默失败

**文件**：`src/storyforge3/prompts/registry.py`

**改动**：

方案 A（推荐）：
1. 在 `_SafeDict.__missing__` 中增加 `warnings.warn(f"Prompt placeholder '{key}' not found in kwargs")` 
2. 保持 `_SafeDict` 仍然返回 `{key}`（向后兼容），但至少有日志提醒

方案 B（更严格）：
1. 给 `render_system_prompt()` 新增参数 `strict: bool = False`
2. `strict=True` 时使用标准 `dict`，占位符未定义直接抛 `KeyError`
3. 测试时可传 `strict=True` 验证所有占位符都有值

**推荐方案 A**（最小改动，向后兼容，有日志输出即可发现问题）。

**额外**：检查现有模板中是否有占位符从未被传入的情况：
- `truth-extract-v2` 模板正文没引用 `{chapter_no}` 但渲染时仍传入 → 无害但冗余，可清理

## 验收标准

| # | 验收项 | 验证方法 |
|---|--------|---------|
| V1 | `CHAPTER_DRAFT_PROMPT` 常量已从 chapter_service.py 删除 | `grep` 确认不存在 |
| V2 | `chapter_service.draft()` 使用注册表 compose 模板 | 阅读代码确认 |
| V3 | `draft()` 走注册表路径后的文本质量不低于原路径 | 需人工对比或跑 ch1 draft 对比（可选，留 P1 验证） |
| V4 | 注册表中只有 7 个模板（无 audit-v1 / length-normalize-v1 / truth-extract-v1） | 读 registry.py 确认 |
| V5 | `LengthNormalizer` 仍正常工作 | 对应测试通过 |
| V6 | 未定义占位符有 warning 日志 | 运行时观察日志 |
| V7 | `pytest` 全量通过 | `python -m pytest -q` |
| V8 | `ruff check` clean | `python -m ruff check .` |
| V9 | 现有 601+ 测试无回归 | 测试数量不减少 |

## 不在本指令范围

- ~~compose-v2 提示词内容升级~~ → P-PROMPT-P1
- ~~llm-audit-v2 维度扩展~~ → P-PROMPT-P1
- ~~plan-v2 结构化输出~~ → P-PROMPT-P1
- ~~truth-extract-v3 hook_updates 增强~~ → P-PROMPT-P1
- ~~提示词外部化~~ → P2
- ~~Context 优先级系统~~ → P2

## 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| draft 统一到 compose-v1 后写作约束减少 | 短期质量可能下降 | P0 只统一来源，P1 立即升级 compose-v2 补回增强约束 |
| 删除孤儿模板导致 import 引用报错 | 构建失败 | 确认无代码引用后再删除；grep 全仓库确认 |
| `draft()` 实际不被 API 调用（只有 workflow 被调用） | P0-1 改动无实际效果 | 先确认调用链再动手 |
