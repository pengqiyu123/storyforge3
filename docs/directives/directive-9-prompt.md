# Directive 9: 提示词质量修复

> PM: Claude Code | 执行: Codex | 级别: 7A 精准修复

## 背景

world_service.py 的"万舌大陆"问题暴露了根因：提示词太空，模型只能产出模板化输出。修复后效果显著。全量审计发现还有 3 个 🔴 空壳提示词和 2 个 🟡 偏弱提示词。

## 问题清单

### 🔴 P0：空壳提示词（必须修复）

**1. `character_service.py` — 角色设计**
- 当前: `"你是中文网文角色设计师。请只输出 JSON。"` (第 12 行)
- 问题: 角色会变成"冷酷少年""温柔学姐"等模板人设
- 修复方向:
  - 角色必须从 seed_brief 的具体场景/事件中诞生，不从标签堆叠
  - personality 必须包含矛盾面（不是"善良"而是"在 X 场景会做 Y，但在 Z 场景会反常"）
  - 禁止"冷酷""温柔""阳光""腹黑"等单标签人格
  - profile 必须包含角色在第一卷会执行的具体行为
  - 角色名字禁止"龙傲天""叶凡"等网文模板名
  - `_schema()` 补充 `properties` 字段类型声明
- 参考: `fanfic_service.py` 的角色档案表（有语癖、说话风格、行为模式、信息边界）

**2. `volume_service.py` — 卷纲规划**
- 当前: `"你是中文网文卷纲规划师。请只输出 JSON。"` (第 12 行)
- 问题: 卷名会变成"觉醒篇""崛起篇""巅峰篇"等模板
- 修复方向:
  - 卷纲必须从 core_conflict 和 power_system 推导，不凭空编
  - 每卷 key_scenes 必须包含至少一个不可逆事件
  - rhythm_curve 必须标注具体情绪目标（不是"高-低-高"而是"第 3 章完成第一次存在感压制"）
  - synopsis 必须回答"这卷结束时主角的处境变了什么"
  - 卷名禁止"觉醒之卷""崛起之卷""巅峰篇""命运篇"等模板
  - `_schema()` 补充 volume 子对象字段和类型声明
- 参考: `chapter_service.py` 的 plan prompt（有目标+关键情节点+节奏）

**3. `chapter_service.py:71` — 起草（最重要的 prompt）**
- 当前: `"你是中文网文作者。直接输出章节正文。"` (第 71 行)
- 问题: 这是整个系统中最重要的 prompt——写出实际正文——却只有一句话
- 修复方向:
  - 明确叙事约束：不用"他感到""他意识到""心中一震"等内心独白标记
  - 明确对话约束：角色说话必须有辨识度，不能所有人都一个腔调
  - 明确节奏约束：场景切换要自然，不能用"与此同时""另一边"硬切
  - 明确禁用：不用总结性语言（"总的来说""就这样"）、不用系统术语
  - 参考 `short-draft-v1` 的禁用表达列表（已有好样本）
  - 注意：这里是内联常量，不是 registry。先升级常量，后续可以考虑迁移到 registry

### 🟡 P1：偏弱提示词（建议修复）

**4. `compose-v1` (registry) — 续写**
- 当前 role: "你是中文网文续写作者，必须服务于既有小说。"
- 修复: 加入与前章承接的具体约束，禁止跳跃和重复

**5. `audit-v1` (registry) — 审计**
- 当前 role: "你是独立中文小说审稿人。"
- 修复: 加入具体审计标准，与 `llm-audit-v1` 的 4 维度对齐但区分机械/语义层次

## 执行范围

### 改
- `src/storyforge3/services/character_service.py`: 升级 `CHARACTER_SYSTEM_PROMPT`、`CHARACTER_TEXT_PROMPT`，补充 `_schema()` properties
- `src/storyforge3/services/volume_service.py`: 升级 `VOLUME_SYSTEM_PROMPT`、`VOLUME_TEXT_PROMPT`，补充 `_schema()` properties
- `src/storyforge3/services/chapter_service.py`: 升级第 71 行的 draft prompt 常量
- `src/storyforge3/prompts/registry.py`: 升级 `compose-v1` 和 `audit-v1` 模板

### 不改
- `WorldConfig`、`Character`、`VolumeOutline`、`ChapterResult` 等 model
- API 路由、前端、MCP tool
- 不做已有数据迁移

### 测试
对每个修改的 service：
- 断言新 prompt 包含关键约束（像 `test_world_service.py` 的做法）
- 断言 `_schema()` 的 required 和 properties 正确
- fallback 路径不受影响（`test_service_json_fallback.py`）
- 全量测试通过

## 验收标准

1. 3 个 🔴 空壳提示词全部升级为有具体约束的版本
2. 2 个 🟡 偏弱提示词得到加强
3. 每个 service 有断言 prompt 内容的测试
4. `pytest -q` 全量通过，`ruff check .` clean
5. `WorldConfig` / `Character` / `VolumeOutline` 等 model 未改
6. API / 前端 / MCP 未改

## 参考：好的提示词标杆

在 `fanfic_service.py` 和 `short-draft-v1` 已有高质量提示词可参考：
- 有具体的字段要求和格式
- 有明确的禁止项
- 有质量判定标准
- 有"信息不足时怎么办"的处理原则
