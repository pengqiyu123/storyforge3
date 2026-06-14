# StoryForge3 动作模块化设计反思

> 📦 **时效性（2026-06-14 审核）：历史归档。** 本反思假设的"UI 动作模块化"前提已被 agent-mode ONLY 取代——动作由 agent/API 驱动，非 UI 封装。保留作设计思路参考，当前方向见 `../current.md` / `../architecture/run-state-and-viewer.md`。

## 1. 文档目的

本文档反思 StoryForge3 当前设计是否应将所有指定动作操作封装为独立、可复用的功能模块。

这里的“动作操作”包括但不限于：

- 创建书籍；
- 删除书籍；
- 更新书籍状态；
- 构建世界观；
- 创建角色；
- 规划卷纲；
- 规划章节；
- 起草章节；
- 审计章节；
- 修订章节；
- 更新章节正文；
- 审批章节；
- 导出章节或整本书；
- 创建快照；
- 恢复快照；
- 备份工作区；
- 恢复工作区；
- Provider 配置验证；
- MCP / Agent 自动调用动作。

目标是判断：StoryForge3 是否需要在现有 Service / API / MCP 之上增加统一的 Action Module 层，以同时满足前端手动交互和 Agent 自动化调用。

---

## 2. 当前设计现状

### 2.1 已有 Service Protocol 边界

当前 [protocols.py](file:///D:/python/Novel/storyforge3/src/storyforge3/services/protocols.py) 已经定义了较清晰的服务接口，包括：

- `BookServiceProtocol`
- `WorldServiceProtocol`
- `CharacterServiceProtocol`
- `VolumeServiceProtocol`
- `ChapterServiceProtocol`
- `AuditServiceProtocol`
- `TruthServiceProtocol`
- `ExportServiceProtocol`
- `PromptServiceProtocol`
- `StyleServiceProtocol`
- `FanficServiceProtocol`
- `ShortStoryServiceProtocol`

这些 Protocol 明确了后端服务边界，并要求：

- 所有服务方法 async；
- 输入输出使用模型对象；
- 不暴露文件系统路径；
- 不暴露 LLM 细节。

这是良好的模块化基础。

### 2.2 API 路由已经按资源拆分

当前 [api/routes](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes) 已经拆分为：

- `books.py`
- `chapters.py`
- `world.py`
- `characters.py`
- `volumes.py`
- `truth.py`
- `snapshots.py`
- `export.py`
- `providers.py`
- `workspace.py`
- `short_story.py`
- `fanfic.py`
- `daemon.py`
- `events.py`
- `health.py`

API 层也已经具备统一响应格式，见 [response.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/response.py)：

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

错误也有统一结构，见 [errors.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/errors.py)。

### 2.3 MCP 工具已有 Agent 入口意识

当前 [mcp/tools.py](file:///D:/python/Novel/storyforge3/src/storyforge3/mcp/tools.py) 已提供多个工具，并在 docstring 中标记：

- 是否只读；
- 是否修改；
- 是否 LLM 调用；
- 是否耗时；
- 前置条件；
- 建议下一步；
- 参数；
- 返回结构。

这说明项目已经意识到前端手动调用和 Agent 自动调用是两个不同入口。

### 2.4 当前缺口

尽管已有 Service / API / MCP 三层，但仍存在一个明显问题：

> 当前“动作”没有被抽象为统一、独立、可复用的 Action Module。API 和 MCP 只是分别调用 Service，动作元信息、权限、风险、确认、幂等、进度、审计、错误分类和返回格式没有统一管理。

尤其是删除、恢复、重写、全流程运行、工作区恢复等高风险动作，如果未来继续分散在 API 路由和 MCP 工具中，会带来维护和安全风险。

---

## 3. 是否应该引入 Action Module 层

结论：**应该引入，但不应一次性重构所有现有 Service。**

推荐策略是：

> 保留现有 Service Protocol 作为业务能力层，在其上新增 Action Module 层，专门承载“可被前端和 Agent 调用的动作单元”。

也就是说，未来的调用关系应从：

```text
Frontend / MCP / CLI
 -> API Route / MCP Tool
 -> Service
```

逐步演进为：

```text
Frontend / MCP / CLI / Agent
 -> Action Adapter
 -> Action Module
 -> Service
```

其中：

- Service 负责领域能力；
- Action Module 负责可执行动作；
- API / MCP / CLI 只是适配器；
- 前端和 Agent 共享同一套动作定义。

---

## 4. 为什么需要 Action Module

### 4.1 前端和 Agent 对动作的需求不同

前端手动调用关注：

- 按钮是否可点；
- 是否需要确认；
- 操作是否危险；
- 进度如何展示；
- 错误如何提示；
- 成功后刷新哪些数据。

Agent 自动调用关注：

- 动作是否只读；
- 是否会修改状态；
- 是否需要用户确认；
- 前置条件是什么；
- 输入 schema 是什么；
- 返回结果能否继续作为下一步输入；
- 失败后应该如何恢复；
- 是否可重试；
- 是否幂等。

如果这些信息只写在 API 文档或 MCP docstring 里，前端和 Agent 很难共享。

### 4.2 高风险动作需要统一治理

删除、恢复、重写、覆盖、导入、工作区恢复等动作都属于高风险操作。

这些动作需要统一处理：

- 确认机制；
- dry-run；
- undo / snapshot；
- 权限或 token；
- 操作日志；
- 影响范围说明；
- Agent 调用限制。

如果每个路由自己实现，长期一定会出现行为不一致。

### 4.3 长任务需要统一进度模型

起草、审计、修订、全流程运行、短篇全流程、自动导演、RAG 重建等都可能是长任务。

它们应共享：

- action_id；
- run_id；
- started / progress / completed / failed 事件；
- cancel；
- retry；
- resume；
- 阶段耗时；
- token 统计；
- 错误原因。

当前 [chapters.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/chapters.py) 中起草章节已经通过 SSE 发布 start / complete / error，但这是局部实现，尚未成为统一动作机制。

### 4.4 文档和测试可以由 Action 元信息驱动

如果每个动作都有统一定义，就可以自动生成：

- 前端按钮权限；
- MCP tool schema；
- API 文档；
- Agent 工具说明；
- 单元测试矩阵；
- 风险清单；
- 用户确认文案。

这会显著提升可维护性。

---

## 5. Action Module 的职责边界

### 5.1 Action Module 应该负责

每个 Action Module 应包含：

1. 动作 ID；
2. 动作名称；
3. 动作分类；
4. 风险等级；
5. 是否只读；
6. 是否修改状态；
7. 是否需要确认；
8. 是否可撤销；
9. 是否幂等；
10. 是否长任务；
11. 输入参数 schema；
12. 输出结果 schema；
13. 前置条件校验；
14. 执行逻辑；
15. 错误分类；
16. 事件发布；
17. 操作日志；
18. Agent 下一步建议。

### 5.2 Action Module 不应该负责

Action Module 不应替代 Service。

它不应该直接承担：

- LLM 底层调用细节；
- 文件路径拼接；
- 存储格式细节；
- Truth 数据库细节；
- 审计规则内部实现；
- 导出格式内部实现。

这些仍应留在 Service、storage、truth、audit、export 等领域模块中。

---

## 6. 推荐目录结构

建议新增：

```text
src/storyforge3/actions/
  __init__.py
  base.py
  registry.py
  errors.py
  context.py
  results.py
  books.py
  chapters.py
  world.py
  characters.py
  volumes.py
  truth.py
  export.py
  snapshots.py
  workspace.py
  providers.py
  short_story.py
  fanfic.py
```

其中：

| 文件 | 作用 |
|---|---|
| `base.py` | Action 基类、元信息、输入输出协议 |
| `registry.py` | Action 注册表，供 API / MCP / Agent 查询 |
| `errors.py` | Action 级错误分类 |
| `context.py` | 当前调用上下文，如 user、source、confirm、dry_run、trace_id |
| `results.py` | 统一返回结构 |
| `books.py` | 书籍相关动作 |
| `chapters.py` | 章节相关动作 |
| `workspace.py` | 高风险工作区动作 |
| `providers.py` | Provider 配置、验证动作 |

---

## 7. Action 基础接口设计

建议定义统一接口：

```python
class ActionRisk(str, Enum):
    READ = "read"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ActionMeta:
    action_id: str
    title: str
    description: str
    category: str
    risk: ActionRisk
    read_only: bool
    mutates_state: bool
    requires_confirmation: bool
    supports_dry_run: bool
    supports_undo: bool
    idempotent: bool
    long_running: bool
    agent_callable: bool


@dataclass(frozen=True)
class ActionContext:
    source: Literal["web", "mcp", "cli", "agent"]
    trace_id: str
    confirmed: bool = False
    dry_run: bool = False
    user_intent: str | None = None


@dataclass(frozen=True)
class ActionResult[T]:
    ok: bool
    action_id: str
    data: T | None = None
    error: ActionError | None = None
    warnings: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    affected_resources: tuple[str, ...] = ()
```

每个具体动作实现：

```python
class DeleteBookAction(Action[DeleteBookInput, DeleteBookOutput]):
    meta = ActionMeta(
        action_id="book.delete",
        title="删除书籍",
        description="删除指定书籍及其章节、truth、导出和状态文件。",
        category="books",
        risk=ActionRisk.DESTRUCTIVE,
        read_only=False,
        mutates_state=True,
        requires_confirmation=True,
        supports_dry_run=True,
        supports_undo=True,
        idempotent=False,
        long_running=False,
        agent_callable=False,
    )

    async def execute(self, input: DeleteBookInput, ctx: ActionContext) -> ActionResult[DeleteBookOutput]:
        ...
```

---

## 8. 输入参数设计原则

### 8.1 所有输入必须显式建模

不建议使用随意的 `dict` 作为动作输入。应使用 Pydantic 或 dataclass 定义。

例如删除书籍：

```python
class DeleteBookInput(BaseModel):
    book_id: str
    create_snapshot: bool = True
    expected_title: str | None = None
```

### 8.2 所有路径型参数必须禁止直接暴露

前端和 Agent 不应传入文件系统路径。

应传入：

- book_id；
- chapter_no；
- snapshot_id；
- provider_name；
- export_format。

路径解析仍由 Service / StoragePaths 负责。

### 8.3 高风险动作应要求确认字段

例如：

```python
class ConfirmedActionInput(BaseModel):
    confirm_text: str | None = None
```

删除书籍可以要求：

```text
confirm_text == book_id
```

或：

```text
confirm_text == expected_title
```

Agent 模式默认不允许执行破坏性动作，除非用户在当前会话显式授权。

---

## 9. 错误处理机制

### 9.1 建议引入 ActionErrorCode

```python
class ActionErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    STATE_CONFLICT = "STATE_CONFLICT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
```

### 9.2 错误返回应包含恢复建议

```python
@dataclass(frozen=True)
class ActionError:
    code: ActionErrorCode
    message: str
    recoverable: bool
    retryable: bool
    next_steps: tuple[str, ...]
```

例如删除未确认：

```json
{
  "code": "CONFIRMATION_REQUIRED",
  "message": "删除书籍需要确认。请传入 confirm_text=book_id。",
  "recoverable": true,
  "retryable": false,
  "next_steps": ["重新提交并确认删除", "或取消操作"]
}
```

---

## 10. 返回结果格式

建议 ActionResult 同时服务前端和 Agent。

示例：

```json
{
  "ok": true,
  "action_id": "chapter.draft",
  "data": {
    "book_id": "wslrj_20260611",
    "chapter_no": 1,
    "text": "...",
    "char_count": 2630
  },
  "warnings": [],
  "next_steps": [
    "调用 chapter.audit 审计章节",
    "或在编辑器中手动修改正文"
  ],
  "affected_resources": [
    "book:wslrj_20260611",
    "chapter:wslrj_20260611:1"
  ]
}
```

Agent 可以读取 `next_steps` 继续行动，前端可以读取 `affected_resources` 决定刷新哪些 query。

---

## 11. 动作分类建议

### 11.1 只读动作

| 动作 ID | 说明 |
|---|---|
| `book.list` | 列出书籍 |
| `book.get` | 获取书籍详情 |
| `chapter.status` | 获取章节状态 |
| `truth.latest` | 获取最新 Truth |
| `export.preview` | 导出预览 |
| `workspace.validate` | 校验工作区 |

### 11.2 低风险写动作

| 动作 ID | 说明 |
|---|---|
| `book.create` | 创建书籍 |
| `book.update_status` | 更新书籍状态 |
| `world.update` | 更新世界观 |
| `character.update` | 更新角色 |
| `chapter.update_text` | 手动保存章节正文 |

### 11.3 中风险 LLM 动作

| 动作 ID | 说明 |
|---|---|
| `world.build` | 构建世界观 |
| `character.create` | 创建角色 |
| `volume.plan` | 规划卷纲 |
| `chapter.plan` | 规划章节 |
| `chapter.draft` | 起草章节 |
| `chapter.audit` | 审计章节 |
| `chapter.revise` | 修订章节 |
| `short_story.run_full_pipeline` | 运行短篇全流程 |

### 11.4 高风险动作

| 动作 ID | 说明 |
|---|---|
| `chapter.rework` | 全文重写 |
| `chapter.approve` | 审批定稿 |
| `snapshot.restore` | 恢复快照 |
| `workspace.restore` | 恢复整个工作区 |
| `provider.import` | 导入 Provider 配置 |

### 11.5 破坏性动作

| 动作 ID | 说明 |
|---|---|
| `book.delete` | 删除书籍 |
| `chapter.delete` | 删除章节 |
| `snapshot.delete` | 删除快照 |
| `truth.delete_chapter` | 删除章节 Truth |
| `workspace.reset` | 重置工作区 |

破坏性动作默认不应允许 Agent 自动调用。

---

## 12. 删除功能的推荐设计

删除功能最能体现 Action Module 的必要性。

### 12.1 删除书籍

动作 ID：`book.delete`

风险等级：`DESTRUCTIVE`

建议行为：

1. 默认要求确认；
2. 默认先创建 snapshot 或 zip backup；
3. 支持 dry-run；
4. 返回将删除的资源清单；
5. 记录操作日志；
6. Agent 默认不可调用；
7. 若允许 Agent 调用，必须要求显式用户确认。

输入：

```json
{
  "book_id": "wslrj_20260611",
  "expected_title": "我是路人甲",
  "create_backup": true,
  "confirm_text": "wslrj_20260611"
}
```

输出：

```json
{
  "deleted": true,
  "book_id": "wslrj_20260611",
  "backup_path": "...",
  "deleted_resources": [
    "book.json",
    "chapters/",
    "truth/",
    "exports/",
    "state/"
  ]
}
```

### 12.2 删除章节

动作 ID：`chapter.delete`

建议行为：

1. 删除章节正文前创建章节级 snapshot；
2. 同步删除或标记对应 truth；
3. 更新 chapter state；
4. 返回受影响资源；
5. 若删除已 approve 章节，风险升级。

### 12.3 删除 Truth

动作 ID：`truth.delete_chapter`

建议谨慎开放。

Truth 删除会影响跨章连续性，建议默认只允许：

- 开发模式；
- 修复模式；
- 或通过专门维护工具调用。

---

## 13. 前端调用方式

前端可以有两种方式。

### 13.1 保持现有 REST API

短期不需要打破现有路由。

可以让路由内部改为调用 Action：

```python
@router.post("/{book_id}/delete")
async def delete_book(req: DeleteBookRequest):
    result = await action_registry.execute("book.delete", req, ActionContext(source="web"))
    return ok(result)
```

### 13.2 增加通用 Action Endpoint

中长期可提供：

```http
POST /actions/{action_id}
```

请求：

```json
{
  "input": {},
  "dry_run": false,
  "confirmed": true
}
```

该接口适合内部前端、CLI 和 Agent 调度，但公开文档仍可保留资源式 API。

---

## 14. Agent 调用方式

Agent 不应直接绕过 Action Module 调 Service。

MCP Tool 应由 Action Registry 自动或半自动生成。

每个 Agent 可见动作应受以下字段控制：

- `agent_callable`
- `read_only`
- `risk`
- `requires_confirmation`
- `long_running`

建议规则：

| 风险等级 | Agent 默认权限 |
|---|---|
| READ | 可直接调用 |
| LOW | 可调用 |
| MEDIUM | 可调用，但需说明成本 |
| HIGH | 需要用户确认 |
| DESTRUCTIVE | 默认不可调用，除非显式授权 |

---

## 15. 文档要求

每个 Action 应有接口文档，至少包含：

1. action_id；
2. 名称；
3. 描述；
4. 风险等级；
5. 是否只读；
6. 是否需要确认；
7. 是否长任务；
8. 输入 schema；
9. 输出 schema；
10. 前置条件；
11. 失败情况；
12. 副作用；
13. Agent 调用限制；
14. 示例请求；
15. 示例返回。

建议新增自动生成文档：

```text
docs/actions/index.md
docs/actions/book.delete.md
docs/actions/chapter.draft.md
docs/actions/workspace.restore.md
```

---

## 16. 测试要求

每个 Action Module 应至少有以下测试：

### 16.1 输入校验测试

验证无效 book_id、chapter_no、format、mode 等是否返回 `INVALID_INPUT`。

### 16.2 前置条件测试

例如：

- 未创建书籍不能起草章节；
- 无正文不能审计；
- 未确认不能删除；
- 审计未通过不能 approve。

### 16.3 成功路径测试

验证动作正常执行并返回正确结构。

### 16.4 错误映射测试

验证 Service 抛出的异常能被转成稳定 ActionError。

### 16.5 副作用测试

验证文件、状态、truth、snapshot、export 是否被正确更新。

### 16.6 Agent 权限测试

验证高风险和破坏性动作不能被 Agent 默认调用。

---

## 17. 推荐实施顺序

不建议一次性重构全项目。建议分阶段实施。

### Phase A：建立 Action 基础设施

1. 新增 `actions/base.py`；
2. 新增 `actions/registry.py`；
3. 新增 `ActionMeta`、`ActionContext`、`ActionResult`、`ActionError`；
4. 先注册 3 个只读动作：`book.list`、`book.get`、`chapter.status`。

### Phase B：迁移章节核心动作

迁移：

- `chapter.plan`
- `chapter.draft`
- `chapter.audit`
- `chapter.revise`
- `chapter.update_text`

目标是让 Web 和 MCP 共用同一套 Action。

### Phase C：实现删除和恢复动作

新增：

- `book.delete`
- `chapter.delete`
- `snapshot.restore`
- `workspace.restore`

重点做确认、dry-run、backup、操作日志。

### Phase D：长任务统一化

统一：

- draft；
- revise；
- run_full_pipeline；
- short_story.run_full_pipeline；
- future director workflow。

加入：

- run_id；
- progress events；
- cancel；
- retry；
- resume。

### Phase E：文档和 MCP 自动生成

由 Action Registry 生成：

- MCP tools；
- docs/actions；
- 前端 action metadata；
- 测试矩阵。

---

## 18. 最终判断

StoryForge3 当前已经有较好的 Service Protocol、API 路由和 MCP 工具基础，但还缺少统一的动作抽象。

如果项目只面向人工前端操作，当前设计短期可用；但 StoryForge3 的定位已经包含 MCP、Agent、自动导演、长任务、工作区恢复和未来自动化生产，因此继续只依赖分散路由和 MCP wrapper 会逐渐暴露问题。

最终建议：

> 应该引入独立、可复用的 Action Module 层，但要采用渐进式迁移，不要推翻现有 Service 架构。

优先级判断：

1. **P0：高风险动作治理**  
   删除、恢复、重写、工作区恢复必须有统一确认、dry-run、backup 和日志。

2. **P1：章节核心动作迁移**  
   plan、draft、audit、revise、update_text 应优先变成 Action，供 Web 和 MCP 复用。

3. **P1：长任务统一运行模型**  
   起草、修订、全流程、自动导演必须支持 run_id、进度、失败恢复和结果记录。

4. **P2：Action Registry 驱动文档与 MCP**  
   中长期让 Action 元信息生成接口文档、Agent 工具说明和前端按钮规则。

引入 Action Module 后，StoryForge3 的架构将更适合未来的自动导演、Agent 操作和真实产品化交付。
