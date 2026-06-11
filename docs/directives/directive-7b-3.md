# Codex 指令：Phase 7B-3 — 导出预览

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7B-2 完成（478 tests: 422 后端 + 56 前端, ruff clean）

---

## 任务概述

让作者在导出前预览格式化效果。当前导出是"点按钮 → 下载文件"的黑箱，作者无法确认格式是否正确、章节标题是否对、番茄/起点格式差异在哪里。本阶段实现"选择格式 → 预览 → 确认导出"的最小闭环。

**当前状态**：
- `PlatformFormatter.format_chapter()` 已有番茄格式化逻辑（标题拼接 + Markdown 清洗 + 段落整理）
- `export/markdown.py` + `export/qidian.py` + `export/epub_format.py` 分别处理各格式
- `POST /export` 端点直接返回 FileResponse，无预览接口
- 前端 `exportsApi.exportBook()` 直接触发下载，无预览 UI
- `ChapterEditor` 组件已支持只读预览模式

**核心原则**：
1. **预览是只读的**——不修改任何数据，只展示格式化结果
2. **复用现有格式化器**——`PlatformFormatter` 等已有，只加一个不写文件的调用路径
3. **单章预览优先**——不做全书预览（全书可能几十章，太大）
4. **用 ChapterEditor 只读模式展示**——复用 7A-1 已有的编辑器组件

---

## Part 1：后端 — 预览 API

### 1.1 `GET /api/books/{book_id}/chapters/{chapter_no}/export-preview`

**文件**：`src/storyforge3/api/routes/chapters.py`（在现有端点旁新增）

```python
class ExportPreviewResponse(BaseModel):
    chapter_no: int
    format: str           # "tomato_txt" | "markdown" | "qidian_txt"
    preview_text: str     # 格式化后的完整文本
    char_count: int       # 中文字符数
    format_errors: list[str]  # check_format() 返回的错误列表


@router.get("/{chapter_no}/export-preview")
async def export_preview(
    book_id: str,
    chapter_no: int,
    fmt: str = "tomato_txt",
    service: ChapterService = Depends(get_chapter_service),
):
```

**行为**：

1. 调用 `service.get_status(book_id, chapter_no)` 获取章节正文
2. 章节不存在 → 404
3. 根据 `fmt` 参数选择格式化器：
   - `tomato_txt` → `PlatformFormatter().format_chapter(title, chapter_no, text)`
   - `markdown` → `format_markdown_chapter(chapter_no, text)`
   - `qidian_txt` → `format_qidian_chapter(chapter_no, text)`
4. 如果 `fmt` 不在支持列表中 → 400 `INVALID_PARAMETER`
5. 对番茄格式运行 `check_format()` 获取格式错误列表
6. 返回 `ExportPreviewResponse`

**不写文件**——这是纯粹的内存格式化 + 返回。

### 1.2 格式化器导入

```python
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.export.markdown import format_markdown_chapter
from storyforge3.export.qidian import format_qidian_chapter
```

这些模块已存在，无需新建。

### 1.3 不改 Protocol

预览是 API 层的便捷方法，直接组合已有 Service + 格式化器，不新增 Service 方法。

---

## Part 2：前端 — 预览对话框

### 2.1 API 层

**文件**：`web/src/api/chapters.ts`

```typescript
export interface ExportPreview {
  chapter_no: number;
  format: string;
  preview_text: string;
  char_count: number;
  format_errors: string[];
}

export const chaptersApi = {
  // ... 现有函数 ...
  exportPreview: (bookId: string, chapterNo: number, fmt = "tomato_txt") =>
    api.get<ExportPreview>(`/api/books/${bookId}/chapters/${chapterNo}/export-preview?fmt=${fmt}`),
};
```

### 2.2 ExportPreviewDialog 组件

**新文件**：`web/src/components/export/ExportPreviewDialog.tsx`

**布局**：

```
┌───────────────────────────────────────────────────────┐
│  导出预览 — 第 3 章                          [关闭 ✕] │
├───────────────────────────────────────────────────────┤
│  格式：[番茄小说 ▼]     字数：2654     ⚠ 1 个格式问题 │
├───────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────┐  │
│  │  第三章 系统觉醒                                   │  │
│  │                                                    │  │
│  │  林默站在教室后排，看着黑板上的数学题...              │  │
│  │                                                    │  │
│  │  （格式化后的正文，使用 ChapterEditor 只读模式）     │  │
│  └─────────────────────────────────────────────────┘  │
├───────────────────────────────────────────────────────┤
│  ⚠ 格式问题：word_count_out_of_range                  │
│                              [复制全文]  [导出下载]   │
└───────────────────────────────────────────────────────┘
```

**Props**：

```typescript
interface ExportPreviewDialogProps {
  bookId: string;
  chapterNo: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
```

**核心逻辑**：

1. Dialog 打开时调用 `chaptersApi.exportPreview(bookId, chapterNo, selectedFormat)`
2. 格式下拉选择（番茄小说 / Markdown / 起点中文），切换时重新请求
3. 预览区域复用 `ChapterEditor` 只读模式展示格式化后文本
4. `format_errors` 非空时在底部显示警告
5. "复制全文"按钮：`navigator.clipboard.writeText(preview.preview_text)`
6. "导出下载"按钮：调用 `exportsApi.exportBook(bookId, { fmt: selectedFormat })` 触发下载

### 2.3 ChapterPipeline 集成

**文件**：`web/src/components/chapters/ChapterPipeline.tsx`

在导出按钮旁（或在步骤条导出步骤处）添加"预览"按钮：

```tsx
<Button variant="ghost" size="sm" onClick={() => setPreviewOpen(true)}>
  <Eye className="h-3 w-3 mr-1" />
  预览
</Button>
```

仅当章节有正文（`hasText`）时可用。

---

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| **格式化器** | `export/formatter.py` PlatformFormatter | 38 行 | **直接复用** `format_chapter()` + `check_format()` |
| **Markdown 格式化** | `export/markdown.py` | 16 行 | **直接复用** `format_markdown_chapter()` |
| **起点格式化** | `export/qidian.py` | 20 行 | **直接复用** `format_qidian_chapter()` |
| **API 路由模式** | `api/routes/export.py` | 64 行 | **复用结构**：Depends + req + error handling |
| **Dialog 组件模式** | `web/src/components/ui/dialog.tsx` | 66 行 | **直接复用** Radix Dialog（shadcn） |
| **只读编辑器展示** | `web/src/components/editor/ChapterEditor.tsx` | — | **直接复用** `readOnly` 模式 |
| **格式选择下拉** | CC-Switch `BackupListSection.tsx:186-224` Select | ~40 行 | **移植骨架**：Select + SelectContent + SelectItem |
| **复制到剪贴板** | AI-Novel-Writing-Assistant `NovelPreview.tsx` copyActiveChapter | ~5 行 | **直接复制** `navigator.clipboard.writeText()` |
| **预览 vs 导出按钮分离** | manuskript `exporter.py` btnPreview + btnExport | — | **复用模式**：先预览再导出 |

**新写比例**：约 **20%**。格式化器 100% 复用现有代码，API 只是把格式化器的结果返回而不写文件，前端 Dialog 复用 shadcn + ChapterEditor + CC-Switch Select 模式。真正新写的是组合胶水代码。

---

## 验收标准

### 后端

- [ ] `GET /{chapter_no}/export-preview?fmt=tomato_txt` 返回格式化预览
- [ ] 支持 `fmt=tomato_txt` / `fmt=markdown` / `fmt=qidian_txt` 三种格式
- [ ] 不支持的 `fmt` → 400 错误
- [ ] 番茄格式返回 `format_errors`（来自 `check_format()`）
- [ ] 不写文件（纯内存格式化）
- [ ] 现有 422 tests 不退步

### 前端

- [ ] `ExportPreviewDialog` 展示格式化预览文本
- [ ] 格式下拉切换重新请求
- [ ] `format_errors` 非空时显示警告
- [ ] "复制全文"按钮可用
- [ ] "导出下载"按钮触发下载
- [ ] `ChapterPipeline` 有"预览"按钮入口

### 测试

- [ ] 后端：`GET /export-preview` API 测试（各格式 + 错误格式 + 章节不存在）
- [ ] 前端：`ExportPreviewDialog` 渲染测试
- [ ] 前端：`chaptersApi.exportPreview` 函数测试
- [ ] 478 基线 tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] `pnpm build` clean（除已知 CodeMirror chunk 警告）
- [ ] `pnpm test` 全绿

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 后端 API | `routes/chapters.py` | ~30 行（端点 + 模型） |
| 后端测试 | `test_api_chapters.py` | ~25 行 |
| 前端 API | `api/chapters.ts` | ~10 行 |
| 前端 ExportPreviewDialog | `ExportPreviewDialog.tsx` | ~70 行 |
| 前端 ChapterPipeline | `ChapterPipeline.tsx` | ~8 行 |
| 前端测试 | `__tests__/` | ~30 行 |
| **合计** | **~6 个文件** | **~175 行** |

---

## 不做的事（Out of Scope）

- ❌ 不做全书预览——只预览单章
- ❌ 不做 EPUB 预览——EPUB 是二进制格式，无法文本预览
- ❌ 不做预览编辑——预览是只读的
- ❌ 不做自定义格式模板——只用已有 3 种格式
- ❌ 不改 `ExportService`——预览不走 Service 层
