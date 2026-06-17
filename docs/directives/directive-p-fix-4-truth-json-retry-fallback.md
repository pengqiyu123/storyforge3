# P-FIX-4：truth_extract JSON 解析降级 + 重试

> 指令编号：P-FIX-4
> 下发时间：2026-06-17
> 下发人：ZCode（PM）
> 执行人：Trae / Codex
> 优先级：P0（生产阻塞项）

---

## 1. 问题陈述

truth_extract 连续两章（ch4、ch5）遇到 `invalid JSON response`，导致 truth 无法自动提取，只能手工补。

根因：`generate_json` 在 LLM 返回非法 JSON 时直接抛 `LLMResponseFormatError`，没有重试；`TruthExtractor.extract` catch 后直接 raise `TruthExtractionError`，没有降级机制。

这是生产阻塞项——每章都要手工补 truth 不可接受。

## 2. 根因分析（PM 已核验代码）

```
TruthExtractor.extract (extractor.py:23-31)
  → client.generate_json (llm_service.py:262-297)
    → generate_text → LLM 返回文本
    → _extract_json_object (llm_service.py:78) 提取 JSON
    → json.loads 失败 → raise LLMResponseFormatError (L292-293)
      ← 没有重试
  ← catch Exception → raise TruthExtractionError (extractor.py:30)
    ← 没有降级
```

## 3. 目标

两层防御：

1. **generate_json 加重试**：JSON 解析失败时，带"上一轮的错误响应"重试一次，让 LLM 修正
2. **TruthExtractor 加降级**：如果重试后仍然失败，用宽松解析尝试提取部分有效字段（至少保住 fact_assertions）

## 4. 改动范围

### 4.1 generate_json 加重试

**文件**：`src/storyforge3/llm/llm_service.py` L262-297

```python
async def generate_json(
    self,
    task_name,
    system_prompt,
    user_payload,
    response_schema,
    *,
    model=None,
    timeout=None,
    max_json_retries=1,  # 新增参数
    **kwargs,
) -> dict:
    last_error_text = ""
    for attempt in range(max_json_retries + 1):
        try:
            if attempt == 0:
                text = await self.generate_text(
                    task_name, system_prompt, user_payload,
                    model=model, timeout=timeout,
                    response_schema=response_schema, **kwargs,
                )
            else:
                # 重试：带上上一轮的错误响应，让 LLM 修正
                retry_payload = {
                    **dict(user_payload),
                    "response_schema": response_schema,
                    "format_instruction": "请只输出一个合法 JSON object，不要 Markdown，不要解释。",
                    "previous_invalid_response": last_error_text,
                    "correction_instruction": "上一轮响应无法解析为 JSON，请修正并只输出合法 JSON object。",
                }
                text = await self.generate_text(
                    task_name, system_prompt, retry_payload,
                    model=model, timeout=timeout, **kwargs,
                )
        except (LLMProviderError, ProviderUnavailableError):
            if attempt >= max_json_retries:
                raise
            fallback_payload = {
                **dict(user_payload),
                "response_schema": response_schema,
                "format_instruction": "请只输出一个合法 JSON object，不要 Markdown，不要解释。",
            }
            text = await self.generate_text(task_name, system_prompt, fallback_payload, model=model, timeout=timeout, **kwargs)

        try:
            data = json.loads(_extract_json_object(text))
        except json.JSONDecodeError as exc:
            last_error_text = text[:500]  # 保留截断的错误响应
            if attempt >= max_json_retries:
                raise LLMResponseFormatError(f"{task_name}: invalid JSON response after {attempt + 1} attempts") from exc
            continue  # 重试
        if not isinstance(data, dict):
            raise LLMResponseFormatError(f"{task_name}: JSON response is not an object")
        _validate_response_schema(data, response_schema, task_name)
        return data
    # 不应该到达这里
    raise LLMResponseFormatError(f"{task_name}: exhausted JSON retries")
```

### 4.2 TruthExtractor 加宽松降级

**文件**：`src/storyforge3/truth/extractor.py`

在 `extract` 方法中，如果 `generate_json` 重试后仍失败，尝试宽松解析：

```python
async def extract(
    self,
    chapter_no: int,
    chapter_text: str,
    previous_truth: TruthData | None = None,
) -> TruthData:
    template = self.registry.get_latest("truth_extract")
    system_prompt = self.registry.render_system_prompt(template, chapter_no=chapter_no)
    payload = {
        "chapter_no": chapter_no,
        "chapter_text": chapter_text,
        "previous_truth": previous_truth.fact_assertions if previous_truth else (),
    }
    try:
        data = await self.client.generate_json(
            "truth_extract",
            system_prompt,
            payload,
            self._schema(),
            prompt_version=f"{template.prompt_id}:v{template.version}",
            max_json_retries=2,  # truth 提取重试 2 次
        )
    except Exception as primary_exc:
        # 降级：用 generate_text + 宽松解析尝试救回
        try:
            data = await self._lenient_extract(chapter_no, chapter_text, system_prompt, previous_truth)
        except Exception:
            raise TruthExtractionError(chapter_no, str(primary_exc)) from primary_exc
    return self._parse(chapter_no, data)

async def _lenient_extract(
    self,
    chapter_no: int,
    chapter_text: str,
    system_prompt: str,
    previous_truth: TruthData | None,
) -> dict:
    """宽松降级：用 generate_text 拿到纯文本，再用正则提取 JSON。"""
    payload = {
        "chapter_no": chapter_no,
        "chapter_text": chapter_text,
        "previous_truth": previous_truth.fact_assertions if previous_truth else (),
        "format_instruction": "请只输出一个合法 JSON object，不要 Markdown，不要解释。",
    }
    text = await self.client.generate_text("truth_extract", system_prompt, payload)
    from storyforge3.llm.llm_service import _extract_json_object
    import json
    candidate = _extract_json_object(text)
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("lenient extract returned non-object")
    return data
```

## 5. 验收标准

- [ ] `generate_json` 在 JSON 解析失败时自动重试（默认 1 次）
- [ ] 重试时带上 `previous_invalid_response` 和 `correction_instruction`
- [ ] `TruthExtractor` 在 `generate_json` 失败后尝试 `_lenient_extract` 降级
- [ ] 降级成功时返回有效 `TruthData`，`source` 字段标记为 `"runtime_lenient"`（区分降级提取）
- [ ] 降级也失败时抛 `TruthExtractionError`（保持现有行为）
- [ ] 后端测试覆盖：正常路径 + 重试路径 + 降级路径 + 全部失败路径
- [ ] 后端测试全量通过（≥638 passed）
- [ ] ruff clean

## 6. 不在本指令范围

- ❌ 不改 truth_extract 提示词内容
- ❌ 不改 truth 存储/检索逻辑
- ❌ 不改前端

## 7. 风险

- 低风险：重试增加 LLM 调用次数，但只在失败时触发
- 降级解析可能提取到不完整的 truth——用 `source="runtime_lenient"` 标记，后续可人工复查
