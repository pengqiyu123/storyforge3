from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.llm.provider_config import ProviderConfigManager
from storyforge3.prompts.registry import create_default_registry

from diagnostics import describe_prompt

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _provider_summary(config: StoryForge3Config) -> dict[str, object]:
    manager = ProviderConfigManager(Path(config.providers_config_dir))
    provider = manager.get_active_provider() or {}
    return {
        "label": provider.get("label"),
        "base_url": provider.get("base_url"),
        "model_id": provider.get("model_id"),
        "format": provider.get("cc_api_format"),
        "candidates": provider.get("cc_endpoint_candidates"),
        "has_api_key": bool(provider.get("api_key")),
    }


async def run_probe(*, attempts: int, interval_seconds: float, timeout: int | None) -> int:
    config = StoryForge3Config()
    llm = create_llm_service(config)
    registry = create_default_registry()
    prompt = registry.render_system_prompt(registry.get_latest("plan"), chapter_no=1)
    payload = {
        "book_id": "provider-plan-probe",
        "chapter_no": 1,
        "context": (
            "题材：都市玄幻。核心设定：存在感系统会影响他人注意力，"
            "异常检测中心负责记录和处理失控能力。主线：林默在检测中心副楼发现残痕机制。"
        ),
    }
    print(f"[DIAG] provider={_provider_summary(config)}", flush=True)
    describe_prompt("provider consecutive plan probe path=LLMService.generate_text task=chapter_plan", prompt, payload)
    failures = 0
    for index in range(1, attempts + 1):
        print(f"[DIAG] provider plan probe {index}/{attempts} start", flush=True)
        started = time.perf_counter()
        try:
            text = await llm.generate_text("chapter_plan", prompt, payload, model=config.model_for_task("planner"), timeout=timeout)
            print(
                f"[DIAG] provider plan probe {index}/{attempts} ok "
                f"elapsed={time.perf_counter() - started:.2f}s preview={text[:120]}",
                flush=True,
            )
        except Exception as exc:
            failures += 1
            print(
                f"[DIAG] provider plan probe {index}/{attempts} error "
                f"elapsed={time.perf_counter() - started:.2f}s {exc.__class__.__name__}: {exc}",
                flush=True,
            )
        if index < attempts:
            await asyncio.sleep(interval_seconds)
    print(f"[DIAG] provider plan probe summary attempts={attempts} failures={failures}", flush=True)
    return 0 if failures == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout", type=int)
    args = parser.parse_args()
    return asyncio.run(run_probe(attempts=args.attempts, interval_seconds=args.interval_seconds, timeout=args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
