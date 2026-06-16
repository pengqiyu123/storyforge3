# 提交指令：P-UI-FIX-1 + P-PROMPT-P0 合并提交

> PM 提交指令 | 2026-06-16

## 背景

P-UI-FIX-1（前端可见性修复）和 P-PROMPT-P0（提示词结构清理）均已实现并 PM 核验通过，但都未提交。两者的代码改动在 `chapter_service.py` 和 `test_chapter_service.py` 中交织，无法用 `git add -p` 非交互拆分。

## 执行步骤

### Step 1：确认工作区状态

```bash
cd D:\python\Novel\storyforge3
git status
git diff --stat
```

确认改动文件列表包含：
- `src/storyforge3/prompts/registry.py`（P-PROMPT-P0）
- `src/storyforge3/services/chapter_service.py`（P-UI-FIX-1 + P-PROMPT-P0）
- `tests/test_chapter_service.py`（P-UI-FIX-1 + P-PROMPT-P0）
- `tests/test_prompt_registry.py`（P-PROMPT-P0）
- `tests/test_service_alignment.py`（P-PROMPT-P0）
- 其他 P-UI-FIX-1 前端/web 相关文件（如有）

### Step 2：一次性提交

```bash
git add -A
git commit -m "feat: P-UI-FIX-1 frontend visibility + P-PROMPT-P0 prompt cleanup

P-UI-FIX-1 (frontend visibility fix):
- ChapterCard uses useChapterStatus hook for real chapter data
- ChapterPipeline mounts AuditResultPanel, RevisionDiffPanel
- Backend GET /status exposes audit_result field
- ChapterService persists audit results after audit stage

P-PROMPT-P0 (prompt structure cleanup):
- Unified draft: removed CHAPTER_DRAFT_PROMPT, draft() uses registry compose
- Removed orphan templates: audit-v1, length-normalize-v1, truth-extract-v1
- Registry reduced from 10 to 7 active templates
- _SafeDict now warns on undefined placeholders

600 tests passed, ruff clean."
```

### Step 3：确认提交

```bash
git log --oneline -1
git status  # 应为 clean
```

### Step 4：推送到远程

```bash
git push origin main
```

如果推送失败（网络/SSL），启用 VPN 后重试。
