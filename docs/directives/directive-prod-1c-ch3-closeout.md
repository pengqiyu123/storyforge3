# 指令 PROD-1c：ch3 closeout 重跑（approve → export）

> 下发 Codex。前置：P-FIX-3（RemoteProtocolError 重试）✅、ch2 exported ✅。
> 任务：关闭 ch3。ch3 正文已由 PM 接受（2702 字），状态 `audited`，缺 truth + export。P-FIX-3 已给 route 内补指数退避重试（5 次），应能覆盖火山 provider 瞬态断连。

## 当前状态

- Book ID：`别打了w帮你们翻译还不行吗_20260611`
- ch3 状态：`audited`
- ch3 正文：`chapters/0003.md` ✅（2702 字）
- truth：❌ 无 `chapter-0003.json`
- export：❌ 无 `chapter-0003.txt`

## 任务

写一次性脚本 `scripts/closeout_ch3.py`，用 service 层执行两步：

```python
"""一次性：ch3 approve(truth) + export。用完即删。"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storyforge3.config import StoryForge3Config
from storyforge3.services.chapter_service import ChapterService

BOOK_ID = "别打了w帮你们翻译还不行吗_20260611"

async def main():
    service = ChapterService(StoryForge3Config())
    print(f"ch3 当前状态: {service._workflow_status(BOOK_ID, 3).value}")

    # step 1: approve（truth 提取 + 状态双跳到 truth_committed）
    result = await service.approve(BOOK_ID, 3)
    print(f"approve 完成: status={result.status.value}, truth={result.truth is not None}")
    if result.truth:
        print(f"  facts: {len(result.truth.fact_assertions)}, chars: {len(result.truth.source)}")

    # step 2: export
    path = await service.export(BOOK_ID, 3)
    print(f"export: {path}")

    # 最终状态
    for ch in (1, 2, 3):
        print(f"ch{ch}: {service._workflow_status(BOOK_ID, ch).value}")

if __name__ == "__main__":
    asyncio.run(main())
```

执行脚本，回报：
- approve 结果（status / truth 是否成功 / 耗时）
- 如果失败：错误信息 + 重试情况
- export 结果
- 三章最终状态

## 红线

- ❌ 不改动引擎代码。
- ❌ 脚本不 commit。
- ❌ 不动 ch1/ch2。
- ❌ 不产 ch4。

## 回报

- ch3 approve 输出（成功/失败、truth 统计）
- ch3 export 路径
- 三章最终状态
- 失败时：完整错误信息
