# Codex 指令：Phase 8B-1 — Service 测试补齐

> 发出日期：2026-06-11
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 8A-1 完成（448+ tests, ruff clean）

---

## 任务概述

为 3 个缺少独立测试的 Service 补齐单元测试，达到 Service 层 100% 测试覆盖。

**当前状态**：
- 17 个 Service 中 14 个有独立测试文件
- 3 个缺失：`PromptService`、`StyleService`、`TruthService`
- 这 3 个 Service 通过其他服务的集成测试间接覆盖，但缺少边界条件测试

---

## Part 1：调研 — 确认 Service 接口

在写测试前，先读取以下文件确认公开接口：

1. `src/storyforge3/services/prompt_service.py` — 完整阅读，记录所有公开方法
2. `src/storyforge3/services/style_service.py` — 完整阅读，记录所有公开方法
3. `src/storyforge3/services/truth_service.py` — 完整阅读，记录所有公开方法
4. `src/storyforge3/services/protocols.py` — 找到这 3 个 Service 的 Protocol 定义
5. 现有测试目录 `tests/` — 确认无重复测试文件

---

## Part 2：测试编写

### 2.1 `tests/test_prompt_service.py`

**测试范围**（根据实际接口调整）：

```python
# 预估测试用例（PromptService 通常是 registry 的轻量包装）：
# - 初始化：从 registry 构造
# - get_prompt()：正常获取存在的 prompt
# - get_prompt()：不存在的 prompt 抛出 KeyError 或返回默认
# - list_prompts()：返回所有可用 prompt 列表
# - 边界：空 registry
```

### 2.2 `tests/test_style_service.py`

**测试范围**：

```python
# 预估测试用例（StyleService 管理风格分析/模仿/守卫）：
# - 初始化：从 config 构造
# - analyze_style()：正常返回风格分析结果
# - get_style_profile()：存在/不存在的 book_id
# - 相关的 style contract / guard / imitation 逻辑（如果由 service 直接调用）
# - 边界：无效 book_id
```

注意：如果 `test_style_contract.py`、`test_style_guard.py`、`test_style_imitation.py` 已覆盖了 StyleService 的底层逻辑，这里主要测试 Service 层的编排和接口。

### 2.3 `tests/test_truth_service.py`

**测试范围**：

```python
# 预估测试用例（TruthService 管理真相提取/查询/持久化）：
# - 初始化：从 config 构造
# - extract_truth()：正常提取（mock LLM）
# - get_truth()：存在/不存在的 book_id + chapter_no
# - list_truth_entries()：按 book_id 过滤
# - 边界：空 truth store、无效 chapter_no
```

注意：`test_truth_database.py`、`test_truth_extractor.py`、`test_truth_retriever.py` 已覆盖底层逻辑，这里主要测试 Service 层的协调。

---

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 借鉴方式 |
|---------|---------|---------|
| **Service 测试模式** | `tests/test_export_service.py` | **直接复用**：`tmp_path` fixture + Service 构造 + 公开方法调用 + 结果断言 |
| **Service 构造模式** | `tests/test_workspace_service.py` | **直接复用**：`make_config()` helper + 直接实例化 Service |
| **LLM mock 模式** | `tests/test_audit_service.py` | **模式复用**：mock LLM 返回固定 JSON + 验证 Service 处理逻辑 |

**新写比例**：约 **80%**。测试代码本身无法从其他项目移植，但测试模式从本项目的现有测试中复用。

---

## 验收标准

### 测试文件

- [ ] `tests/test_prompt_service.py` 存在，至少 5 个测试用例
- [ ] `tests/test_style_service.py` 存在，至少 5 个测试用例
- [ ] `tests/test_truth_service.py` 存在，至少 5 个测试用例
- [ ] 每个测试文件覆盖该 Service 的所有公开方法
- [ ] 边界条件有覆盖（空数据、无效输入、默认值）

### 质量

- [ ] 所有新增测试通过
- [ ] 现有 448+ tests 不退步
- [ ] `ruff check .` clean
- [ ] 无外部依赖 mock 泄漏（mocks 在 fixture/afterEach 中清理）

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| PromptService 测试 | `tests/test_prompt_service.py` | ~60 行 |
| StyleService 测试 | `tests/test_style_service.py` | ~60 行 |
| TruthService 测试 | `tests/test_truth_service.py` | ~60 行 |
| **合计** | **3 个文件** | **~180 行** |

---

## 不做的事（Out of Scope）

- ❌ 不改 Service 实现代码（仅写测试）
- ❌ 不改 Protocol 定义
- ❌ 不改现有测试（除非发现现有测试与新测试冲突）
- ❌ 不做 100% 行覆盖（目标 80%+ 公开方法覆盖）
- ❌ 不引入新的测试依赖
