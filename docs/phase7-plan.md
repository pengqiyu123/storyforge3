# Phase 7 规划：从管线引擎到写作工作台

> 产品经理：Claude Code PM
> 日期：2026-06-10
> 前置里程碑：Phase 6 完成（438 tests, 395 后端 + 39 前端 + 4 Rust）

---

## 战略方向

Phase 1-6 构建了完整的后端引擎 + 前端 MVP + 桌面端 + MCP 集成。**Phase 7 的核心目标是让真实作者能日常使用。**

当前状态：作者可以触发自动化管线（plan → draft → audit → revise → export），但无法参与编辑、审阅、修订对比、质量追踪等人工环节。前端是一个"管线控制台"，不是"写作工作台"。

Phase 7 将前端从"管线控制台"升级为"写作工作台"，同时推进 MCP 实战化和打包发布。

---

## 差距分析摘要

| 能力 | 后端 | 前端 | 差距 |
|------|------|------|------|
| 章节编辑+保存 | ✅ API 存在 | ❌ 编辑器只用于只读预览 | **编辑后无法保存** |
| 审计问题定位 | ✅ 36 规则返回行级 detail | ❌ AuditResultPanel 只显示 rule_id | **无法跳转到问题行** |
| 修订 Diff | ❌ 无 diff 生成 | ❌ 无 diff 展示 | **完全缺失** |
| 导出预览 | ✅ 格式化后文本可获取 | ❌ 只有下载按钮 | **无法预览** |
| 版本回滚 | ✅ 快照系统存在（5 份） | ❌ 无快照 UI | **后端有但前端看不到** |
| Truth 可视化 | ✅ API 完整 | ❌ 无 UI | **后端有但前端看不到** |
| MCP 错误建议 | ⚠️ 简单 ValueError | — | **错误信息缺少恢复建议** |
| 打包发布 | ⚠️ tauri.conf 配置了 | ❌ 无 CI/CD、无签名 | **手动构建** |

---

## Phase 7 子阶段

### 执行顺序：7A → 7B → 7C → 7D

```
Phase 7A: 写作工作台（编辑 + 审计定位 + Diff + 保存）   ~8 天
Phase 7B: 质量运营面板（Truth 可视化 + 快照回滚 + 导出预览） ~6 天
Phase 7C: MCP 实战化（错误建议 + playbook + Claude 注册）   ~4 天
Phase 7D: 打包发布（CI/CD + 签名 + 首个 release）         ~5 天
```

---

## Phase 7A：写作工作台（~8 天）

### 目标

让作者能手动编辑章节、定位审计问题、查看修订 diff、保存修改。从"管线控制台"到"写作工作台"的关键一步。

### 拆分

#### 7A-1：章节编辑 + 保存（~3 天）

**后端**：
- `PUT /api/books/{book_id}/chapters/{chapter_no}/text` — 接受 `{ text: string }`，保存到 `chapters/{no}.md`，更新 `actual_chars`
- `ChapterService.update_text(book_id, chapter_no, text)` — 新增方法

**前端**：
- `ChapterEditor` 切换到可编辑模式（`readOnly={false}`）
- 添加"编辑"按钮切换模式
- 编辑时显示保存状态（未保存/已保存/保存中）
- 保存时调用 `chaptersApi.updateText()`
- 编辑后自动失效 React Query 缓存

**借鉴**：CC-Switch `WorkspaceFileEditor.tsx`（96 行）的 load → edit → save 流程。

#### 7A-2：审计问题定位 + 高亮（~3 天）

**状态**：✅ 完成（2026-06-10）

**后端**：
- 段落相关机械规则在失败 detail 中返回 `paragraph_indices` + `snippet`
- `AuditResponse` 返回完整 `rule_results`，前端可直接读取定位信息

**前端**：
- `AuditResultPanel` 增强：点击可定位失败项，滚动到编辑器对应位置
- 编辑器中高亮审计问题段落（使用 CodeMirror decoration）
- 按严重程度分色：BLOCKING 红色、WARNING 黄色

**借鉴**：CodeMirror 6 的 `ViewPlugin` + `Decoration` API（CC-Switch 可能已有类似实现）。

**验收结果**：406 后端 tests + 47 前端 tests 通过，ruff clean，pnpm build clean（仅 Vite/CodeMirror chunk size 警告）。Rust 4 tests 为既有基线，本轮环境未安装 `cargo`，未复跑。

#### 7A-3：修订 Diff 展示（~2 天）

**状态**：✅ 完成（2026-06-10）

**后端**：
- `ChapterService.revise()` 改为执行真实修订（复用 `ChapterWorkflow.step_revise()`）
- 修订前写入 `{chapter_no}.before.md` 快照；`update_text()` 也同样保存快照
- `build_revision_diff()` 使用 `split_paragraphs()` + `SequenceMatcher` 生成段落级 replace / insert / delete blocks
- `POST /api/books/{book_id}/chapters/{chapter_no}/revise` 响应内联 `revision_diff`

**前端**：
- 新增 `RevisionDiffPanel` 组件：左右对比（before/after）
- 在 `ChapterPipeline` 的修订步骤后展示 diff
- replace 左红右绿，insert 右绿，delete 左红

**借鉴**：后端复用 `ChapterWorkflow.step_revise()`，前端复用现有 `Card` / `Badge` / `Button` 体系，不引入新依赖。

**验收结果**：412 后端 tests + 50 前端 tests 通过，ruff clean，pnpm build clean（仅 Vite/CodeMirror chunk size 警告）。Rust 4 tests 为既有基线，本轮环境未安装 `cargo`，未复跑。

### 验收标准

- [ ] 作者可以手动编辑章节文本并保存
- [x] 审计问题可以跳转到编辑器对应位置
- [x] 编辑器中高亮显示审计问题段落
- [x] 修订后显示 before/after diff
- [x] 462 个本轮可运行 tests 不退步（412 后端 + 50 前端）；Rust 4 tests 既有基线未复跑

---

## Phase 7B：质量运营面板（~6 天）

### 目标

让作者能查看跨章连续性数据、回滚到历史版本、预览导出格式。

### 拆分

#### 7B-1：Truth 可视化面板（~3 天）

**前端**：
- 新增 `TruthPanel` 组件：在 BookDetailPage 的新 tab 中展示
- 展示内容：fact_assertions（事实）、character_updates（角色变化）、irreversible_facts（不可逆事实）、hook_updates（钩子）
- 按章节分组展示 truth 历史
- 支持搜索/过滤事实

**API**：已有 `truthApi.latest()` + `truthApi.byChapter()` + `truthApi.extract()`

#### 7B-2：快照管理 + 回滚（~2 天）

**后端**：
- `GET /api/books/{book_id}/snapshots` — 列出快照
- `POST /api/books/{book_id}/snapshots/{snapshot_id}/restore` — 回滚到快照
- `SnapshotService.list()` + `SnapshotService.restore()`

**前端**：
- 在 BookDetailPage 新增"版本历史"tab
- 快照列表（时间戳 + 章节号 + 文件数）
- 回滚按钮（需确认对话框）

**借鉴**：后端 `snapshot.py` 已有快照创建逻辑，只需加 list/restore。

#### 7B-3：导出预览（~1 天）

**后端**：
- `POST /api/books/{book_id}/export/preview` — 返回格式化后的文本（不写文件）

**前端**：
- 导出前显示预览（使用 ChapterEditor readOnly 模式）
- 格式选择 → 预览 → 确认导出

### 验收标准

- [ ] Truth 面板可查看事实断言和角色变化
- [ ] 快照列表可查看历史版本
- [ ] 可回滚到指定快照
- [ ] 导出前可预览格式化文本

---

## Phase 7C：MCP 实战化（~4 天）

### 目标

让 15 个 MCP tool 真正可被 Claude Code / Codex 串联使用，形成完整创作 playbook。

### 拆分

#### 7C-1：错误建议 + 输出增强（~2 天）

**后端（tools.py 改进）**：
- 错误信息增加恢复建议：`"书籍不存在: {book_id}。请先调用 create_book 创建。"`
- 输出模型增加 `next_step` 字段（可选）：`get_chapter_status` 返回时建议下一步操作
- `draft_chapter` 返回时包含字数统计和审计预检提示

#### 7C-2：只读/危险操作分层 + Claude Code 注册（~2 天）

**后端**：
- Tool 描述中标注操作类型：`[只读]` / `[创建]` / `[LLM 调用，可能耗时数分钟]`
- 危险操作（`run_full_pipeline`、`revise`）在描述中说明不可逆性

**配置**：
- 提供 `claude mcp add` 注册命令文档
- 可选：提供 `.claude/settings.json` MCP 配置片段

### 验收标准

- [ ] 所有错误信息包含恢复建议
- [ ] Tool 描述标注操作类型和耗时
- [ ] 提供 Claude Code 注册文档

---

## Phase 7D：打包发布（~5 天）

### 目标

让 StoryForge3 可以作为桌面应用分发，支持自动更新。

### 拆分

#### 7D-1：CI/CD + 签名（~3 天）

- GitHub Actions workflow：push tag → build → sign → release
- Windows: code signing certificate (或先用 self-signed)
- macOS: Apple Developer signing + notarization
- 自动上传到 GitHub Releases
- 更新 `latest.json` 供 Tauri updater 使用

#### 7D-2：用户数据管理（~2 天）

- 首次启动引导（选择工作区目录）
- 数据目录结构验证和修复
- 备份/恢复功能（一键导出/导入工作区）
- 从 zip 恢复快照

### 验收标准

- [ ] `cargo tauri build` 成功产出安装包
- [ ] GitHub Actions 自动构建
- [ ] 首次启动有引导流程
- [ ] 用户可备份和恢复工作区

---

## 时间线

```
Week 1-2:  7A 写作工作台（编辑 + 审计定位 + Diff）
Week 3:    7B 质量运营面板（Truth + 快照 + 导出预览）
Week 4:    7C MCP 实战化 + 7D 打包发布
总计：~23 天工作量，4-5 周自然时间
```

---

## 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Diff 展示前端复杂度高 | 中 | 工期+50% | 使用成熟 React diff 组件库 |
| CodeMirror 审计高亮实现复杂 | 中 | 工期+30% | 先做简单行滚动，高亮后续迭代 |
| Tauri 签名需要 Apple Developer 账号 | 高 | 7D 阻塞 | 先做 Windows，macOS 后续 |
| Truth 可视化信息量大，UI 难设计 | 中 | 工期+20% | 先做列表展示，可视化后续 |

---

## 建议执行顺序

**7A-1 → 7A-2 → 7A-3 → 7B-1 → 7B-2 → 7B-3 → 7C-1 → 7C-2 → 7D-1 → 7D-2**

7A 优先级最高——没有编辑和保存，作者无法参与创作过程。7D 放最后——打包发布依赖前面功能稳定。
