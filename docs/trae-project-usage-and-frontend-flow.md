# Trae：StoryForge3 项目使用流程与前端呈现流程梳理

> 适用范围：StoryForge3 当前 Web/Tauri 工作台  
> 依据：当前前端路由、页面组件、章节 Run Viewer、Provider 面板、书籍详情页、短篇页与设置页实现  
> 核心定位：StoryForge3 已从“手动按钮式章节管线”转向 **agent-mode-first / agent-mode-only 的长篇生产工作台**。前端主要承担配置、查看、人工编辑和诊断职责。

---

## 1. 当前产品使用流程总览

StoryForge3 当前应被理解为三类交互面共同组成的创作系统：

```text
Setup 面：用户手动配置和初始化项目
Production 面：agent/API 驱动章节生产，前端只查看
Authoring 面：用户手动编辑正文、查看结果、处理确认与修正
```

### 1.1 Setup 面：一次性配置与创作准备

用户在 Setup 面完成以下工作：

1. 启动应用；
2. 导入或切换 AI Provider；
3. 创建长篇书籍项目；
4. 构建或编辑世界观；
5. 创建角色；
6. 规划卷纲；
7. 查看书籍基础信息和准备状态。

这些操作允许用户手动触发，因为它们属于“项目配置”和“创作准备”，不是正式章节生产流水线。

### 1.2 Production 面：agent/API 生产章节

长篇章节生产不再由用户在 UI 中逐步点击“规划、起草、审计、修订、导出”完成。

当前正确模型是：

```text
agent/API 触发 run
  → 后端执行 plan/draft/audit/revise/approve/truth/export
  → SSE 推送运行事件
  → 前端 Run Viewer 展示进度和产物
```

前端章节页中的“规划/起草/审计/修订/批准/导出”现在应理解为 **阶段查看标签**，不是运行按钮。

### 1.3 Authoring 面：用户人工编辑与结果查看

用户仍然可以：

- 查看章节规划；
- 查看正文；
- 手动编辑正文；
- `Ctrl+S` 保存；
- 查看运行状态；
- 查看 Truth；
- 查看快照；
- 预览导出格式。

人工编辑是长期保留能力，不与 agent-mode 冲突。

---

## 2. 推荐用户使用流程

### 2.1 首次启动

用户打开 StoryForge3 后，前端会进入应用主路由。

如果是 Tauri 桌面环境：

```text
Tauri 启动后端 sidecar / venv fallback
  → 前端等待 /api/health
  → 成功进入工作台
  → 失败显示 StartupErrorScreen
```

如果启动失败，用户看到的不是普通业务页面，而是启动错误页。

### 2.2 配置 Provider

路径：

```text
/settings
```

用户流程：

1. 进入“设置”；
2. 在“AI 供应商”面板点击“导入”；
3. 从 CC-Switch 数据库读取可用 provider；
4. 选择 provider 并导入；
5. 切换 active provider；
6. 点击验证，确认 provider 可用。

前端呈现：

- Provider 列表；
- 当前 active provider 标识；
- enabled / 未配置状态；
- 验证按钮；
- 移除按钮；
- CC-Switch 导入弹窗。

当前注意点：

- 导入弹窗仍需进一步优化无 key provider 的过滤和禁选；
- Provider 配置路径应保证导入 API 与 LLM runtime 读取同一路径；
- 不应在 UI 或日志中暴露完整 API key。

### 2.3 创建长篇书籍

路径：

```text
/books
```

用户流程：

1. 进入“我的小说”；
2. 点击创建书籍；
3. 填写书名、类型、平台、章节目标、单章字数等；
4. 创建后进入书籍详情页。

前端呈现：

- 书籍列表；
- 创建书籍弹窗；
- 加载态和错误提示；
- 每本书可进入详情页。

### 2.4 准备世界观

路径：

```text
/books/{book_id}?tab=world
```

用户流程：

1. 输入一句种子设定；
2. 点击“构建世界观”；
3. 系统生成世界观草案；
4. 用户手动编辑：
   - 设定；
   - 力量体系；
   - 核心冲突；
   - 世界规则；
5. 点击保存。

前端呈现：

- 左侧：世界观构建输入；
- 右侧：世界观编辑区；
- 保存按钮；
- 构建成功 toast。

定位：Setup 面，允许用户手动触发。

### 2.5 准备角色

路径：

```text
/books/{book_id}?tab=characters
```

用户流程：

1. 点击创建角色；
2. 输入角色需求或描述；
3. 系统生成角色档案；
4. 用户查看角色卡；
5. 展开角色查看：
   - 性格；
   - 能力；
   - 弧线；
6. 查看关系网络。

前端呈现：

- 角色卡片网格；
- 主角/主要/次要标签；
- 展开详情；
- 关系网络卡片。

定位：Setup 面，允许用户手动触发。

### 2.6 准备卷纲

路径：

```text
/books/{book_id}?tab=volumes
```

用户流程：

1. 输入卷数；
2. 输入总章节数；
3. 点击“规划卷”；
4. 系统生成卷纲；
5. 用户查看每卷：
   - 卷名；
   - 章节数；
   - 摘要；
   - 关键场景；
   - 节奏曲线。

前端呈现：

- 左侧：卷数和总章节输入；
- 右侧：卷纲列表；
- 每卷卡片展示 synopsis/key scenes/rhythm。

定位：Setup 面，允许用户手动触发。

### 2.7 由 agent/API 生产章节

长篇章节生产的推荐流程：

```text
用户准备好 world / characters / volumes
  → agent 或外部 API 触发章节 run
  → 后端执行章节生产
  → 前端章节页查看运行进度和产物
```

当前章节页不再建议用户手动点击运行按钮。

章节生产阶段包括：

1. 规划 plan；
2. 起草 draft；
3. 审计 audit；
4. 修订 revise；
5. 批准 approve；
6. Truth 提取/提交；
7. 导出 export。

### 2.8 查看章节结果

路径：

```text
/books/{book_id}?tab=chapters
```

当前章节列表已经改为基于 reconciliation 的真实产物视图。

展示逻辑：

```text
读取 /books/{book_id}/reconcile
  → 显示真实存在产物的章节
  → 按卷分组展示
  → 显示 inconsistent 章节警告
  → 末尾显示“下一章由 agent 触发生产”
```

前端呈现：

- 顶部真实产物章数；
- 数据不一致数量；
- 卷分组；
- 章节卡片；
- 下一章提示卡。

章节卡片展示：

- 第几章；
- 规划/正文/Truth/导出产物是否存在；
- 当前状态；
- 数据不一致原因；
- 展开后进入 ChapterPipeline。

### 2.9 章节 Run Viewer

章节卡片展开后进入 Run Viewer。

当前 Run Viewer 包含：

1. RunTrack：运行阶段轨道；
2. LiveStage：当前运行阶段；
3. 阶段查看标签：规划、起草、审计、修订、批准、导出；
4. SSE 实时进度；
5. 流式正文显示；
6. 章节正文编辑器；
7. 导出预览。

重要规则：

```text
阶段标签只负责查看结果，不触发运行。
```

阶段标签中的勾选表示该阶段已有产物，不表示按钮可点击执行。

### 2.10 用户手动编辑正文

在章节 Run Viewer 的“起草”阶段：

1. 如果已有正文，用户可以点击“编辑”；
2. 修改正文；
3. 点击保存或按 `Ctrl+S`；
4. 保存时使用 content hash 防止覆盖冲突；
5. 保存失败会显示错误。

这是 Authoring 面的核心能力。

### 2.11 查看 Truth

路径：

```text
/books/{book_id}?tab=truth
```

用户流程：

1. 查看所有章节 Truth；
2. 按章节筛选；
3. 搜索事实、角色、钩子；
4. 查看：
   - 不可逆事实；
   - 钩子；
   - 事实断言；
   - 角色更新；
   - 关系更新；
   - 备注。

前端呈现：

- 搜索框；
- 章节筛选 pill；
- 每章 Truth 卡片；
- 多个事实分类区块。

### 2.12 查看和恢复快照

路径：

```text
/books/{book_id}?tab=snapshots
```

用户流程：

1. 查看快照列表；
2. 点击刷新；
3. 选择某个快照回滚；
4. 二次确认；
5. 执行恢复。

前端呈现：

- 快照时间；
- 关联章节；
- 文件数量；
- 回滚按钮；
- 确认对话框。

注意：回滚会覆盖当前正文和状态，属于高风险操作。

---

## 3. 前端页面结构

当前前端路由：

```text
/                DashboardPage
/books           BooksPage
/books/:id       BookDetailPage
/shorts          ShortsPage
/shorts/:id      ShortDetailPage
/settings        SettingsPage
*                redirect /
```

### 3.1 DashboardPage：首页生产状态

功能：

- 展示项目概览；
- 展示书籍数量；
- 展示连载中数量；
- 展示 provider 状态；
- 展示最近活动；
- 提供快捷入口。

当前入口：

- 打开我的小说；
- 构建世界观；
- 运行全流程。

建议：

```text
“运行全流程”当前实际只是跳转章节页，建议改为“查看章节进度”或“打开生产看板”。
```

### 3.2 SettingsPage：设置页

组成：

- ProviderPanel；
- WorkspaceSettings。

主要功能：

- 导入 CC-Switch provider；
- 切换 provider；
- 验证 provider；
- 移除 provider；
- 管理工作区恢复/备份相关能力。

### 3.3 BooksPage：长篇书籍列表

组成：

- CreateBookDialog；
- BookList。

功能：

- 展示长篇书籍；
- 创建新书；
- 进入书籍详情。

### 3.4 BookDetailPage：长篇项目工作台

顶部展示：

- 返回按钮；
- 书名；
- 类型/平台/状态；
- 章节进度条。

Tabs：

```text
概览 / 世界观 / 角色 / 卷规划 / 章节 / 真相 / 快照
```

各 tab 职责：

| Tab | 职责 | 交互类型 |
|---|---|---|
| 概览 | 查看当前章节、目标章节、单章字数 | 查看 |
| 世界观 | 构建和编辑世界观 | Setup 手动 |
| 角色 | 创建和查看角色 | Setup 手动 |
| 卷规划 | 生成和查看卷纲 | Setup 手动 |
| 章节 | 查看章节产物和运行状态 | Production 查看 |
| 真相 | 查看连续性 Truth | 查看 |
| 快照 | 查看和恢复快照 | 高风险手动 |

### 3.5 ChapterList：章节列表

当前已从旧的 `current_chapter + 2` 启发式改为 reconcile 驱动。

职责：

- 读取章节产物一致性；
- 显示真实存在产物的章节；
- 按卷分组；
- 显示 inconsistent 数量；
- 提示下一章由 agent 触发。

### 3.6 ChapterCard：章节卡片

职责：

- 展示章节号；
- 展示产物存在状态；
- 展示章节状态；
- 标注数据不一致；
- 展开后显示 ChapterPipeline。

产物标记：

```text
规划 / 正文 / Truth / 导出
```

### 3.7 ChapterPipeline：章节 Run Viewer

当前定位：

```text
只读运行查看器 + 正文编辑器
```

包含：

- RunTrack；
- LiveStage；
- 阶段查看 tabs；
- PipelineProgress；
- PlanView；
- 正文编辑器；
- PlaceholderView；
- ExportPreviewDialog。

核心规则：

- 不触发章节生产；
- 只展示 agent/API 触发后的进度；
- 用户可以编辑正文；
- 用户可以预览导出格式。

### 3.8 ShortsPage / ShortDetailPage：短篇流程

短篇仍保留按钮式管线：

- 构思；
- 起草；
- 审计；
- 修订；
- 导出；
- 一键运行。

这与长篇 agent-mode-only 不完全一致。

当前判断：

```text
短篇可以暂时保持手动按钮模式，但后续若产品方向完全统一，也应考虑迁移为 Run Viewer 模型。
```

---

## 4. 当前推荐的信息架构

### 4.1 用户心智

建议用户理解为：

```text
设置 provider
  → 创建书
  → 准备世界/角色/卷纲
  → 让 agent 生产章节
  → 前端查看运行和结果
  → 用户手动编辑润色
  → 查看 Truth / 快照 / 导出
```

### 4.2 前端心智

前端不再是“生成按钮集合”，而是：

```text
配置台 + 项目资料编辑台 + 生产状态查看器 + 正文编辑器 + 诊断面板
```

### 4.3 后端/agent 心智

后端和 agent 负责：

```text
实际运行 Action / Run
维护章节状态
写入产物
推送 SSE
记录 RunRecord
提供 reconcile
```

---

## 5. 当前流程中的不一致点

### 5.1 Dashboard 文案仍有误导

“运行全流程”实际是导航链接，不触发运行。

建议改为：

```text
查看章节进度
```

或：

```text
打开生产看板
```

### 5.2 长篇与短篇交互范式不一致

长篇：agent-mode-only，章节页只读查看。  
短篇：仍是按钮式手动管线。

短期可以接受，但文档和 UI 应明确：

```text
短篇仍为轻量手动工作流；长篇为 agent 驱动生产流。
```

### 5.3 阶段产物详情仍未完全落地

ChapterPipeline 中审计、修订、批准、导出阶段仍使用 PlaceholderView，提示 P1 后续补齐。

当前用户能看到阶段存在，但不能完整查看所有阶段详情。

建议后续补齐：

- AuditResult 持久化展示；
- revision diff；
- approval record；
- export record；
- run stage artifacts。

### 5.4 错误提示仍偏短暂

保存失败仍会 3 秒后自动清除。

建议后续 Run Viewer 中错误持久展示，并提供复制诊断信息。

---

## 6. 建议的标准使用路径

### 6.1 新用户路径

```text
打开应用
  → 设置 / 导入 provider
  → 验证 provider
  → 我的小说 / 创建书籍
  → 进入书籍详情
  → 构建世界观
  → 创建主角和核心角色
  → 规划卷纲
  → 通知 agent 开始生产第 1 章
  → 章节页查看 Run Viewer
  → 用户手动编辑正文
  → 查看 Truth
  → 查看快照
```

### 6.2 老项目续写路径

```text
打开 Dashboard
  → 进入最近活动书籍
  → 查看章节列表
  → 检查 reconcile 是否有不一致
  → agent 触发下一章生产
  → 章节页观察运行进度
  → 编辑正文
  → 检查 Truth 是否沉淀
```

### 6.3 Provider 切换路径

```text
设置
  → AI 供应商
  → 导入/刷新
  → 切换 active provider
  → 验证
  → 返回 Dashboard 查看 provider 状态
```

### 6.4 异常恢复路径

```text
章节列表发现数据不一致
  → 展开章节卡片
  → 查看 inconsistent reasons
  → 查看 Run Viewer / Truth / Export 状态
  → 必要时进入快照页恢复
  → 或等待 agent 执行 reconcile/heal 策略
```

---

## 7. 后续优化建议

### P0：文案与路径清晰化

1. Dashboard “运行全流程”改为“查看章节进度”；
2. Provider 设置页显示当前 active provider 和验证状态；
3. 启动日志/健康面板显示 provider 配置路径，但不显示密钥。

### P1：章节 Run Viewer 完整化

1. 审计结果持久化展示；
2. 修订 diff 展示；
3. 批准记录展示；
4. 导出记录展示；
5. 错误持久展示。

### P1：Production 面进一步统一

1. 明确章节页不触发生产；
2. 所有生产动作由 agent/API 触发；
3. 前端仅展示运行状态和产物。

### P2：短篇流程决策

需要决定：

```text
短篇继续保留按钮式轻量流程
还是迁移到和长篇一致的 Run Viewer 模型
```

如果短篇作为轻量功能，可以保留现状；如果要统一产品范式，应迁移。

### P2：新手引导

建议在概览页增加“创作准备清单”：

- Provider 是否可用；
- 世界观是否存在；
- 主角是否存在；
- 卷纲是否存在；
- 是否已有章节；
- 下一章由 agent 触发。

---

## 8. 最终判断

StoryForge3 当前前端已经从旧的“按钮式章节管线”明显转向：

```text
Setup 手动配置
+ Production agent/API 驱动
+ Run Viewer 查看
+ Authoring 手动编辑
```

这个方向是正确的。

当前最需要补齐的是：

1. Dashboard 文案与 agent-mode 对齐；
2. 章节阶段详情持久化展示；
3. Provider 导入和验证体验；
4. 短篇流程是否跟随长篇统一；
5. 新手准备清单。

一句话总结：

> 用户应通过前端完成配置、建书、设定准备、结果查看和人工编辑；章节生产本身由 agent/API 驱动，前端章节页是 Run Viewer，不再是运行按钮面板。
