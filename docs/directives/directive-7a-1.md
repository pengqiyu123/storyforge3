# Codex 指令：Phase 7A-1 — 章节编辑 + 保存

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 6 完成（438 tests: 395 后端 + 39 前端 + 4 Rust, ruff clean）

---

## 任务概述

让作者能手动编辑章节正文并保存修改。这是从"管线控制台"到"写作工作台"的地基——没有编辑和保存，作者无法参与创作过程。

**当前状态**：
- `ChapterEditor` 已支持 `readOnly={false}` + `onChange` 回调（Phase 6A-1 移植）
- `ChapterPipeline` 硬编码 `readOnly`，无编辑模式
- 后端无 `PUT/PATCH` 端点更新章节正文
- `BookStorage._atomic_write_text()` 已实现原子写入（temp + rename）

**本阶段交付**：

1. 后端：章节正文保存 API + `ChapterService.update_text()` + 覆写保护
2. 前端：编辑模式切换 + 保存/放弃 + 脏状态提示
3. 保存后刷新状态和字数

---

## Part 1：后端 — 章节正文保存 API

### 1.1 ChapterService 新增方法

在 `src/storyforge3/services/chapter_service.py` 新增：

```python
async def update_text(self, book_id: str, chapter_no: int, text: str, *, expected_hash: str | None = None) -> ChapterResult:
```

**行为**：

1. **前置检查**：调用 `get_status(book_id, chapter_no)`，章节必须存在且已有正文（`text` 非空）。空章节不允许直接写入（应走 `draft` 管线）
2. **覆写保护**：如果 `expected_hash` 非空，读取当前文件内容，计算 SHA-256 前 8 字符作为 fingerprint，与 `expected_hash` 比较。不匹配则抛 `ValueError("章节内容已被修改，请刷新后重试")`
3. **原子写入**：调用 `self.storage.write_text(self.paths.chapter_file(book_id, chapter_no), text)`
4. **状态转换**：手动编辑后状态转到 `NEEDS_REVIEW`（使用 `state_machine.force_needs_review(book_id, chapter_no, reason="manual_edit")`）
5. **返回**：`ChapterResult(book_id, chapter_no, status=NEEDS_REVIEW, title=..., text=text)`

**Hash 计算**：

```python
import hashlib

def _content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
```

此函数放在 `chapter_service.py` 内作为模块级私有函数。

**借鉴**：`storage.py:71-83` 的 `_atomic_write_text` 模式（temp + rename）。`update_text` 直接复用 `storage.write_text` 即可，它内部已调用原子写入。

### 1.2 Protocol 更新

在 `src/storyforge3/services/protocols.py` 的 `ChapterServiceProtocol` 中新增：

```python
async def update_text(self, book_id: str, chapter_no: int, text: str, *, expected_hash: str | None = None) -> ChapterResult: ...
```

### 1.3 API 端点

在 `src/storyforge3/api/routes/chapters.py` 新增：

```
PUT /{chapter_no}/text
```

**请求体**：

```python
class UpdateTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="章节正文")
    expected_hash: str | None = Field(default=None, description="乐观锁：当前正文的 SHA-256 前 8 位")
```

**响应**：标准信封 `{"ok": true, "data": ChapterResult}`

**错误处理**：
- 章节不存在 → 404 `CHAPTER_NOT_FOUND`
- 章节无正文（空章节）→ 409 `CHAPTER_EMPTY` "空章节请先使用 draft 管线生成正文"
- Hash 不匹配 → 409 `CONTENT_CONFLICT` "章节内容已被修改，请刷新后重试"

### 1.4 状态响应增强

`GET /{chapter_no}/status` 返回的 `ChapterStatusResponse` 新增字段：

```python
content_hash: str | None  # 当前正文 SHA-256 前 8 位，前端保存时回传用于乐观锁
actual_chars: int         # 当前正文中文字符数
```

**`actual_chars` 计算**：复用已有的 `count_chinese_chars()` 函数。

**注意**：如果 `ChapterStatusResponse` 是 Pydantic model，直接加字段。如果是 dict 构造，加到构造逻辑中。

---

## Part 2：前端 — 编辑模式 + 保存

### 2.1 API 层

在 `web/src/api/chapters.ts` 新增：

```typescript
export interface UpdateTextRequest {
  text: string;
  expected_hash?: string;
}

export const chaptersApi = {
  // ... 现有函数 ...
  updateText: (bookId: string, chapterNo: number, data: UpdateTextRequest) =>
    api.put<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/text`, data),
};
```

### 2.2 Hook 层

在 `web/src/hooks/useChapters.ts` 新增 mutation：

```typescript
export function useChapterUpdateText(bookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ chapterNo, text, expectedHash }: {
      chapterNo: number;
      text: string;
      expectedHash?: string;
    }) => chaptersApi.updateText(bookId, chapterNo, {
      text,
      expected_hash: expectedHash,
    }),
    onSuccess: (_result, variables) => {
      // 失效状态缓存，触发重新拉取（刷新字数 + content_hash + status）
      queryClient.invalidateQueries({
        queryKey: chapterStatusKey(bookId, variables.chapterNo),
      });
    },
  });
}
```

**模式**：与现有 `useChapterDraft` / `useChapterRevise` 等完全一致——mutation 成功后 invalidate `chapterStatus` query。

### 2.3 ChapterPipeline 编辑模式改造

**当前**：`ChapterPipeline.tsx:138-143` 硬编码 `<ChapterEditor readOnly>`。

**改为**：

1. 新增内部状态：

```typescript
const [editing, setEditing] = useState(false);
const [editText, setEditText] = useState("");
```

2. 新增"编辑"按钮（与"Plan"/"Draft"按钮同排），仅当 `result?.text` 非空时显示
3. 点击"编辑"时：`setEditText(result.text); setEditing(true)`
4. 编辑模式下 `ChapterEditor` 切换为 `readOnly={false}` + `value={editText}` + `onChange={setEditText}`
5. 编辑模式下显示底部操作栏：

```
[放弃修改]  [保存 (Ctrl+S)]     未保存的修改
```

6. **脏状态**：`editText !== (result?.text ?? "")` → 显示"未保存的修改"提示（橙色文字）
7. **保存**：调用 `useChapterUpdateText` mutation，传入 `expectedHash: result?.content_hash`
8. **放弃**：`setEditing(false); setEditText("")`
9. **保存成功**：自动退出编辑模式 `setEditing(false)`
10. **保存失败（冲突）**：toast 提示"内容已被修改，请刷新"，不退出编辑模式

**按钮状态**：
- 保存按钮：`disabled` 当 `!dirty || isSaving`
- 放弃按钮：`disabled` 当 `isSaving`
- 编辑按钮：`disabled` 当 `editing || !result?.text`

### 2.4 键盘快捷键

在编辑模式下支持 `Ctrl+S` / `Cmd+S` 保存。在 `ChapterPipeline` 的编辑模式下添加 `keydown` 事件监听：

```typescript
useEffect(() => {
  if (!editing) return;
  const handler = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      if (dirty && !isSaving) saveMutation.mutate(...);
    }
  };
  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}, [editing, dirty, isSaving]);
```

### 2.5 ChapterStatusResponse 类型更新

在 `web/src/api/chapters.ts` 的 `ChapterResult` 接口中新增：

```typescript
export interface ChapterResult {
  // ... 现有字段 ...
  content_hash?: string;   // 后端新增
  actual_chars?: number;   // 后端新增
}
```

### 2.6 字数显示更新

`ChapterPipeline` 现有字数显示 `countChineseChars(result?.text ?? "")`。保存后 `result` 会被 React Query 刷新，字数自动更新。无需额外处理。

---

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| 原子写入模式 | `storage.py:71-83` | 13 行 | 直接复用 `write_text()`，无需重写 |
| load→edit→save 流程 | `cc-switch-main/src/components/WorkspaceFileEditor.tsx` | 96 行 | 参考三态模式（loading/editing/saving） |
| React Query mutation | `web/src/hooks/useChapters.ts:17-26` | 10 行 | 复用 `useChapterMutation` 模式 |
| API 路由模式 | `api/routes/chapters.py:302` | ~20 行 | 复用现有路由注册 + 信封响应 |
| 状态机转换 | `state/machine.py:47` | force_needs_review | 直接调用已有方法 |

**新写比例**：约 30%。后端原子写入、状态机、mutation 模式均可直接复用。

---

## 验收标准

### 后端

- [ ] `ChapterService.update_text()` 方法存在，支持 `expected_hash` 乐观锁
- [ ] `PUT /api/books/{book_id}/chapters/{chapter_no}/text` 端点存在
- [ ] 空章节拒绝写入（409 `CHAPTER_EMPTY`）
- [ ] Hash 不匹配拒绝写入（409 `CONTENT_CONFLICT`）
- [ ] 保存后状态转为 `NEEDS_REVIEW`
- [ ] `GET /status` 返回 `content_hash` 和 `actual_chars`
- [ ] `ChapterServiceProtocol` 包含 `update_text` 签名

### 前端

- [ ] `ChapterEditor` 可切换为编辑模式（`readOnly={false}`）
- [ ] 编辑按钮仅在有正文时显示
- [ ] 脏状态提示（橙色文字"未保存的修改"）
- [ ] 保存按钮调用 `updateText` API，传入 `expected_hash`
- [ ] 保存后 `ChapterPipeline` 状态和字数自动刷新
- [ ] 放弃修改可退出编辑模式
- [ ] Ctrl+S / Cmd+S 保存快捷键
- [ ] 冲突时 toast 提示"内容已被修改"

### 测试

- [ ] 后端：`ChapterService.update_text()` 单元测试（正常保存、空章节拒绝、hash 冲突、状态转换）
- [ ] 后端：`PUT /text` API 测试（404/409/200 场景）
- [ ] 后端：`GET /status` 新字段测试
- [ ] 前端：`chaptersApi.updateText` 函数测试
- [ ] 前端：`useChapterUpdateText` hook 测试（成功 invalidation + 冲突处理）
- [ ] 前端：`ChapterPipeline` 编辑/保存/放弃 UI 测试
- [ ] 438 基线 tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] `pnpm build` clean（除已知的 CodeMirror chunk 警告）
- [ ] `pnpm test` 全绿

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 后端 service | `chapter_service.py` | ~30 行（update_text + _content_fingerprint） |
| 后端 protocol | `protocols.py` | ~1 行 |
| 后端 API | `routes/chapters.py` | ~35 行（端点 + 请求模型 + 错误处理） |
| 后端测试 | `test_chapter_service.py` + `test_chapters.py` | ~60 行 |
| 前端 API | `chapters.ts` | ~10 行 |
| 前端 hook | `useChapters.ts` | ~15 行 |
| 前端 UI | `ChapterPipeline.tsx` | ~50 行（编辑模式 + 操作栏 + 快捷键） |
| 前端测试 | `__tests__/` | ~60 行 |
| **合计** | **~8 个文件** | **~260 行** |

---

## 不做的事（Out of Scope）

- ❌ 不做多章节批量编辑
- ❌ 不做编辑历史/撤销（undo/redo 由 CodeMirror 自带）
- ❌ 不做自动保存（本次仅手动保存）
- ❌ 不做 Markdown 预览切换（后续 7A-3 考虑）
- ❌ 不做协同编辑锁（桌面端单人使用，无需协同）
- ❌ 不修改 `ShortPipeline`（短篇编辑是独立需求，后续处理）
