# P-UI-FIX-2：消除 exported 章节的 404 console 噪音

> 指令编号：P-UI-FIX-2
> 下发时间：2026-06-15
> 下发人：ZCode（PM）
> 执行人：Trae（首席开发主管）
> 优先级：P1

---

## 1. 问题陈述

打开已导出（exported）的 ch1/ch2/ch3 章节时，浏览器 console 刷出 404 错误：

```
client.ts:27 GET http://127.0.0.1:8000/api/books/.../chapters/3/run 404 (Not Found)
```

页面功能正常（`useRunRecord` 的 catch 正确处理了 404 并返回 null），但 console 噪音影响开发者体验，且 404 语义错误（章节存在，run 记录不存在）。

## 2. 根因分析（PM 亲自核验）

**数据链路**：
1. 用户点击 ChapterCard 展开章节 → `open=true`
2. `ChapterCard.tsx:67` → `useChapterStatus(bookId, chapterNo, open)` 请求 `/status`
3. `ChapterPipeline.tsx:80` → `useRunRecord(bookId, chapterNo)` 无条件启用，请求 `/run`
4. 后端 `chapters.py:632` → `registry.get_current(book_id, chapter_no)` 返回 None
5. 后端 `chapters.py:634` → `raise chapter_not_found(book_id, chapter_no)` → HTTP 404
6. 前端 `useRunRecord.ts:14-17` catch 住 "not found" 返回 null

**三个问题**：
- 后端用 `chapter_not_found`（语义：章节不存在）表达"run 不存在"，语义错误
- 前端 `useRunRecord` 的 `enabled` 没有状态过滤，任何章节展开都请求
- 对于 exported 章节请求 /run 毫无意义

## 3. 修复方案

### 方案 A（推荐）：前端加 enabled 门禁

**改动文件**：`web/src/hooks/useRunRecord.ts` + `web/src/components/chapters/ChapterPipeline.tsx`

**useRunRecord.ts** — 添加可选 `enabled` 参数：

```typescript
export function useRunRecord(
  bookId: string | undefined,
  chapterNo: number | undefined,
  enabled: boolean = true  // 新增参数
) {
  return useQuery({
    queryKey: runRecordKey(bookId ?? "", chapterNo ?? 0),
    queryFn: async (): Promise<RunRecord | null> => {
      // ... 现有 catch 逻辑不变
    },
    enabled: Boolean(enabled && bookId && chapterNo),  // 加入 enabled 条件
    retry: false
  });
}
```

**ChapterPipeline.tsx** — 只对非 exported 章节启用：

```typescript
// ChapterPipeline.tsx 第 ~80 行
const runRecord = useRunRecord(bookId, chapterNo, status !== "exported");
```

`status` 已在 ChapterPipeline 中可用（第 ~98 行 `const status = String(result?.status ?? "empty").toLowerCase()`），需要提前声明或在 useRunRecord 调用时直接用 result 判断。

### 方案 B（备选）：后端返回 200 + null

**改动文件**：`src/storyforge3/api/routes/chapters.py`

```python
@router.get("/{chapter_no}/run")
async def get_chapter_run(
    book_id: str,
    chapter_no: int,
    registry: RunRegistry = Depends(get_run_registry),
):
    record = registry.get_current(book_id, chapter_no)
    if record is None:
        return ok(None)  # 改为 200 + null，而不是 404
    return ok(_run_record_to_response(record))
```

**选择方案 A**，原因：
- 语义更正确：不请求不存在的数据，比请求后返回 null 更合理
- 减少网络请求：exported 章节根本不需要发 /run 请求
- 方案 B 需要改后端 API 契约（从 404 变为 200+null），可能影响其他客户端

## 4. 改动范围

| 文件 | 改动 |
|------|------|
| `web/src/hooks/useRunRecord.ts` | 添加 `enabled` 参数 |
| `web/src/components/chapters/ChapterPipeline.tsx` | 调用时传入 `status !== "exported"` |

## 5. 验收标准

- [ ] 打开 ch1/ch2/ch3（exported 状态）时，console 不出现 `/run 404` 错误
- [ ] 打开未开始章节（empty）时，console 不出现 `/run 404` 错误
- [ ] 正在运行的章节仍然能正确请求 `/run` 并显示进度
- [ ] 前端测试全部通过（111 passed，不减少）
- [ ] 前端 typecheck 通过

## 6. 不在本指令范围

- ❌ 不修改后端 API 路由
- ❌ 不修改 RunRegistry
- ❌ 不处理 `chapter_not_found` 的语义问题（那是另一个 tech debt）

## 7. 风险

- 极低风险：只改前端 enabled 条件，不影响任何功能逻辑
- 需确认 `status` 变量在 `useRunRecord` 调用时已经可用（可能需要调整声明顺序）

---

## 附录：验证步骤

1. 启动后端 + 前端
2. 打开《别打了》章节列表
3. 展开第 1 章（exported）→ 检查 console 无 404
4. 展开第 2 章（exported）→ 检查 console 无 404
5. 展开第 3 章（exported）→ 检查 console 无 404
6. 展开 empty 章节（如果有）→ 检查 console 无 404
