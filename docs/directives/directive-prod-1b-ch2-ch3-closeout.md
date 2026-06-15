# 指令 PROD-1b：《别打了》ch2/ch3 生产收尾（truth + export 闭环）

> 下发 Codex。前置：P-FIX-1（truth 门禁）✅、P-FIX-2（resume inclusive）✅、P-DISCARD-1 ✅。
> 触发：PROD-1 生产审计发现 ch2 停在 approved（P0.5 旧 approve，无双跳）、ch3 停在 audited（truth 提取因 LLM JSON 不稳定失败）。两章均未 export。本指令关闭两章，为 ch4 生产扫清路径。

## 背景

### 当前数据状态

| 章 | 状态 | 正文 | truth 文件 | truth DB | export | 说明 |
|----|------|------|-----------|----------|--------|------|
| ch1 | exported | ✅ `0001.md` | ✅ `chapter-0001.json` | ✅ | ✅ `chapter-0001.txt` | 已完成 |
| ch2 | **approved** | ✅ `0002.md` | ✅ `chapter-0002.json`（44 entries） | ✅ | ❌ | P0.5 旧 approve，无双跳机制，状态停在 approved |
| ch3 | **audited** | ✅ `0003.md`（2702 字，PM 已接受） | ❌ | ❌ | ❌ | PROD-1 truth 提取因 LLM JSON 不稳定失败 |

Book ID：`别打了w帮你们翻译还不行吗_20260611`

### ch2 特殊情况

ch2 的 truth 文件和 DB 已存在（P0.5 时代 approve 时提取的），但状态停在 `approved` 而非 `truth_committed`。当前 `approve` 端点（`POST /{n}/approve`）门禁检查 action=`"approve"`，但 APPROVED 状态下 `allowed_actions` 返回 `{"truth"}`——**不包含 "approve"**。因此 ch2 不能重新走 approve 端点。

ch2 收尾只需两步：
1. 推进状态 `approved → truth_committed`（truth 已存在，不需重新提取）
2. `export`

### ch3 收尾

ch3 正文已由 PM 接受（2702 字，质量合格），需要走正常 approve→export 流程：
1. `POST /{n}/approve`（truth 提取 + 状态推进 AUDITED→APPROVED→TRUTH_COMMITTED）
2. `POST /{n}/export`

**注意**：ch3 truth 提取依赖 LLM，之前因 ark-code-latest JSON 解析不稳定失败。如果再次失败，按重试策略处理。

## 任务

### 1. 编写收尾脚本（不改动引擎代码）

在项目根创建一次性收尾脚本 `scripts/closeout_ch2_ch3.py`，用 engine 的 service 层直接操作（绕过 API 门禁层的 action 命名不匹配问题）：

```python
"""一次性收尾脚本：关闭 ch2（状态推进+export）和 ch3（approve+export）。
用完即删，不纳入版本管理。"""
import asyncio
import sys
from pathlib import Path

# 确保 project root 在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.services.chapter_service import ChapterService
from storyforge3.state.machine import ChapterStateMachine, ChapterStatus

BOOK_ID = "别打了w帮你们翻译还不行吗_20260611"


async def closeout_ch2(service: ChapterService) -> None:
    """ch2: approved → truth_committed（truth 已存在）→ export"""
    print("=== ch2 收尾 ===")
    status = service._workflow_status(BOOK_ID, 2)
    print(f"  当前状态: {status.value}")

    # 推进状态（truth 文件和 DB 已存在，不重新提取）
    machine = ChapterStateMachine(service.paths.chapter_states(BOOK_ID))
    machine.advance(BOOK_ID, 2, ChapterStatus.TRUTH_COMMITTED)
    print(f"  推进到: {service._workflow_status(BOOK_ID, 2).value}")

    # 导出
    path = await service.export(BOOK_ID, 2)
    print(f"  导出: {path}")
    print("=== ch2 完成 ===")


async def closeout_ch3(service: ChapterService) -> None:
    """ch3: audited → approve(truth提取) → export"""
    print("=== ch3 收尾 ===")
    status = service._workflow_status(BOOK_ID, 3)
    print(f"  当前状态: {status.value}")

    # approve（含 truth 提取 + 状态双跳）
    result = await service.approve(BOOK_ID, 3)
    print(f"  approve 完成: {result.status.value}, truth={result.truth is not None}")

    # 导出
    path = await service.export(BOOK_ID, 3)
    print(f"  导出: {path}")
    print("=== ch3 完成 ===")


async def main() -> None:
    config = StoryForge3Config()
    service = ChapterService(config)

    await closeout_ch2(service)
    print()
    await closeout_ch3(service)

    # 最终状态
    print("\n=== 最终状态 ===")
    for ch in (1, 2, 3):
        status = service._workflow_status(BOOK_ID, ch)
        print(f"  ch{ch}: {status.value}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 2. 执行脚本并回报

执行脚本，回报：
- ch2 状态推进结果
- ch3 approve（truth 提取）结果——**如果 truth 提取失败，报告错误但不中止 ch2**
- ch2/ch3 export 结果
- 最终三章状态

### 3. 验证

脚本执行后：
- `chapter_states.json` 应为 ch1=exported, ch2=exported, ch3=exported
- `truth/chapter-0003.json` 应存在
- `exports/chapter-0002.txt` 和 `exports/chapter-0003.txt` 应存在
- `GET /api/books/{id}/reconcile` 应显示 max=3, valid=3, inconsistent=0

### 4. 清理

- 脚本执行成功后删除 `scripts/closeout_ch2_ch3.py`
- 不 commit 脚本（一次性工具）

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| service 层直接调用 | `chapter_service.py` approve/export | **直接复用** |
| 状态机推进 | `machine.py` advance() | **直接复用** |
| truth 文件已存在 | `truth/chapter-0002.json`（P0.5 时代产出） | **确认不重新提取** |

**新写比例**：约 **90%**（一次性脚本，非引擎代码）。

## 红线

- ❌ **不改动任何引擎代码**——P-FIX-1/2 已修复门禁，本指令只做数据收尾。
- ❌ **不重新提取 ch2 truth**——已存在且正确（44 entries），避免 LLM 不稳定性浪费。
- ❌ 脚本不 commit（一次性工具）。
- ❌ 不动 ch1 数据（已 exported）。
- ❌ 不产 ch4（独立指令 PROD-2）。

## 回报

- ch2 收尾输出（状态推进 + export 路径）
- ch3 approve 输出（truth 提取是否成功 + 耗时）
- ch3 export 输出
- 最终 `chapter_states.json` 三章状态
- `reconcile` 结果截图或输出（max/valid/inconsistent/next_writable）
- 如果 ch3 truth 提取失败：错误信息 + 建议重试方案

## Out of Scope

- ❌ ch4 生产（PROD-2，独立指令）。
- ❌ 引擎代码修改（P-FIX-1/2 已覆盖）。
- ❌ 前端改动。
- ❌ 修复 ch2 状态停在 approved 的根因（P0.5 历史遗留，已通过脚本规避；未来 approve 端点统一后不会再出现）。
