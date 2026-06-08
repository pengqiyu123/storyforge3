"""PROTOTYPE: compare LLM patch output formats on Chinese chapter text.

This is a throwaway diagnostic script. It does not participate in the
production revision pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from typing import Any

from storyforge3.audit.context import build_mechanical_context
from storyforge3.audit.rules import RULE_REGISTRY
from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.llm.provider_config import ProviderConfigManager


SCENARIOS = ("golden_three_hook", "forbidden_patterns")
FORMATS = ("find_replace", "paragraph_index")


@dataclass(frozen=True)
class PrototypeCase:
    name: str
    rule_id: str
    text: str


@dataclass(frozen=True)
class PrototypeResult:
    scenario: str
    patch_format: str
    attempt: int
    parsed: bool
    applicable: bool
    rule_fixed: bool
    latency_seconds: float
    error: str = ""
    patch_summary: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="PROTOTYPE patch format reliability probe.")
    parser.add_argument("--attempts", type=int, default=3, help="Attempts per scenario/format.")
    parser.add_argument("--timeout", type=int, default=120, help="Per LLM request timeout in seconds.")
    parser.add_argument("--interval", type=float, default=2.0, help="Sleep between provider calls.")
    args = parser.parse_args()
    return asyncio.run(run_probe(attempts=args.attempts, timeout=args.timeout, interval=args.interval))


async def run_probe(*, attempts: int, timeout: int, interval: float) -> int:
    config = StoryForge3Config()
    manager = ProviderConfigManager(config.providers_config_dir)
    provider = manager.get_active_provider()
    if provider is None:
        raise SystemExit(f"No active imported provider in {manager.config_path}")

    print("PROTOTYPE patch format probe")
    print(f"Provider: {provider.get('label')}")
    print(f"Base URL: {provider.get('base_url')}")
    print(f"Model: {provider.get('model_id')}")
    print(f"Attempts: {attempts} per scenario/format")
    print()

    llm = create_llm_service(config)
    cases = build_cases()
    for case in cases:
        context = build_mechanical_context(1, case.text)
        before = RULE_REGISTRY[case.rule_id](context)
        print(
            f"[CASE] {case.name}: text_chars={len(case.text)} "
            f"chinese_chars={context.chinese_chars} "
            f"initial_rule_passed={before.passed}"
        )
    print()

    results: list[PrototypeResult] = []
    for case in cases:
        for patch_format in FORMATS:
            for attempt in range(1, attempts + 1):
                result = await probe_one(
                    llm,
                    case,
                    patch_format,
                    attempt=attempt,
                    model=str(provider.get("model_id") or ""),
                    timeout=timeout,
                )
                results.append(result)
                print_result(result)
                if interval > 0:
                    await asyncio.sleep(interval)

    print()
    print_summary(results)
    return 0


async def probe_one(
    llm: Any,
    case: PrototypeCase,
    patch_format: str,
    *,
    attempt: int,
    model: str,
    timeout: int,
) -> PrototypeResult:
    started = time.perf_counter()
    try:
        data = await llm.generate_json(
            "patch_format_prototype",
            system_prompt_for(patch_format),
            user_payload_for(case, patch_format),
            response_schema_for(patch_format),
            model=model or None,
            timeout=timeout,
            temperature=0.2,
            max_output_tokens=900,
        )
    except Exception as exc:  # noqa: BLE001 - prototype needs exact failure counts.
        return PrototypeResult(
            case.name,
            patch_format,
            attempt,
            parsed=False,
            applicable=False,
            rule_fixed=False,
            latency_seconds=time.perf_counter() - started,
            error=f"{type(exc).__name__}: {exc}",
        )

    parsed, parse_error = validate_patch(data, patch_format)
    if not parsed:
        return PrototypeResult(
            case.name,
            patch_format,
            attempt,
            parsed=False,
            applicable=False,
            rule_fixed=False,
            latency_seconds=time.perf_counter() - started,
            error=parse_error,
            patch_summary=summarize_patch(data, patch_format),
        )

    patched, apply_error = apply_patch_data(case.text, data, patch_format)
    if patched is None:
        return PrototypeResult(
            case.name,
            patch_format,
            attempt,
            parsed=True,
            applicable=False,
            rule_fixed=False,
            latency_seconds=time.perf_counter() - started,
            error=apply_error,
            patch_summary=summarize_patch(data, patch_format),
        )

    rule_result = RULE_REGISTRY[case.rule_id](build_mechanical_context(1, patched))
    return PrototypeResult(
        case.name,
        patch_format,
        attempt,
        parsed=True,
        applicable=True,
        rule_fixed=rule_result.passed,
        latency_seconds=time.perf_counter() - started,
        error="" if rule_result.passed else f"target rule still failed: {case.rule_id}",
        patch_summary=summarize_patch(data, patch_format),
    )


def system_prompt_for(patch_format: str) -> str:
    if patch_format == "find_replace":
        return (
            "你是中文网文局部修订器。只输出 JSON object。"
            "输出格式：{\"find\":\"原文中连续存在的片段\",\"replace\":\"替换片段\"}。"
            "find 必须能在原文中精确匹配一次或多次；replace 只包含小说正文。"
        )
    return (
        "你是中文网文局部修订器。只输出 JSON object。"
        "输出格式：{\"paragraph_index\":数字,\"replacement\":\"新段落\"}。"
        "paragraph_index 从 0 开始，replacement 只包含该段替换后的小说正文。"
    )


def user_payload_for(case: PrototypeCase, patch_format: str) -> dict[str, Any]:
    paragraphs = build_mechanical_context(1, case.text).paragraphs
    if case.rule_id == "golden_three_hook":
        instruction = (
            "修复 golden_three_hook：前三段缺少有效钩子。"
            "只改第一段或前三段之一，加入异常、声音、门、发现等有效钩子。"
        )
    else:
        instruction = "修复 forbidden_patterns：删除或改写禁止输出模式，不改变剧情。"
    payload: dict[str, Any] = {
        "patch_format": patch_format,
        "failed_rule": case.rule_id,
        "instruction": instruction,
        "chapter_text": case.text,
    }
    if patch_format == "paragraph_index":
        payload["paragraphs"] = list(paragraphs)
        payload["paragraph_index_is_zero_based"] = True
    return payload


def response_schema_for(patch_format: str) -> dict[str, Any]:
    if patch_format == "find_replace":
        return {
            "type": "object",
            "properties": {
                "find": {"type": "string"},
                "replace": {"type": "string"},
            },
            "required": ["find", "replace"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "paragraph_index": {"type": "integer"},
            "replacement": {"type": "string"},
        },
        "required": ["paragraph_index", "replacement"],
        "additionalProperties": False,
    }


def validate_patch(data: dict[str, Any], patch_format: str) -> tuple[bool, str]:
    if patch_format == "find_replace":
        if not isinstance(data.get("find"), str) or not data["find"].strip():
            return False, "missing non-empty find"
        if not isinstance(data.get("replace"), str) or not data["replace"].strip():
            return False, "missing non-empty replace"
        return True, ""
    if not isinstance(data.get("paragraph_index"), int):
        return False, "paragraph_index is not int"
    if not isinstance(data.get("replacement"), str) or not data["replacement"].strip():
        return False, "missing non-empty replacement"
    return True, ""


def apply_patch_data(text: str, data: dict[str, Any], patch_format: str) -> tuple[str | None, str]:
    if patch_format == "find_replace":
        find = str(data["find"])
        replace = str(data["replace"])
        count = text.count(find)
        if count < 1:
            return None, "find not found"
        return text.replace(find, replace, 1), ""

    paragraphs = list(build_mechanical_context(1, text).paragraphs)
    index = int(data["paragraph_index"])
    if index < 0 or index >= len(paragraphs):
        return None, f"paragraph_index out of range: {index}"
    paragraphs[index] = str(data["replacement"]).strip()
    return "\n\n".join(paragraphs), ""


def summarize_patch(data: dict[str, Any], patch_format: str) -> str:
    if patch_format == "find_replace":
        find = str(data.get("find", ""))
        replace = str(data.get("replace", ""))
        return f"find_len={len(find)} replace_len={len(replace)} find_head={find[:24]!r}"
    return f"paragraph_index={data.get('paragraph_index')} replacement_len={len(str(data.get('replacement', '')))}"


def print_result(result: PrototypeResult) -> None:
    status = "OK" if result.rule_fixed else "FAIL"
    print(
        f"[{status}] scenario={result.scenario} format={result.patch_format} attempt={result.attempt} "
        f"parsed={result.parsed} applicable={result.applicable} fixed={result.rule_fixed} "
        f"latency={result.latency_seconds:.2f}s error={result.error or '-'} patch={result.patch_summary}"
    )


def print_summary(results: list[PrototypeResult]) -> None:
    print("SUMMARY")
    for scenario in SCENARIOS:
        for patch_format in FORMATS:
            selected = [result for result in results if result.scenario == scenario and result.patch_format == patch_format]
            total = len(selected)
            parsed = sum(1 for result in selected if result.parsed)
            applicable = sum(1 for result in selected if result.applicable)
            fixed = sum(1 for result in selected if result.rule_fixed)
            avg_latency = sum(result.latency_seconds for result in selected) / max(total, 1)
            print(
                f"- {scenario}/{patch_format}: "
                f"parsed={parsed}/{total}, applicable={applicable}/{total}, "
                f"target_rule_fixed={fixed}/{total}, avg_latency={avg_latency:.2f}s"
            )


def build_cases() -> tuple[PrototypeCase, PrototypeCase]:
    base = build_base_chapter()
    forbidden = base.replace("陈野把玻璃杯放在桌沿。", "作为AI，陈野把玻璃杯放在桌沿。", 1)
    return (
        PrototypeCase("golden_three_hook", "golden_three_hook", base),
        PrototypeCase("forbidden_patterns", "forbidden_patterns", forbidden),
    )


def build_base_chapter() -> str:
    paragraphs = [
        "林默站在旧楼一层的走廊里，手里攥着刚领到的检测表。纸面被汗浸出浅浅的弯痕，他低头看了一眼，又把它折回口袋。",
        "墙上的白漆剥落成细碎的斑块，值班窗口后面亮着冷白的灯。排队的人不多，每个人都压低语调，像怕惊动什么规矩。",
        "陈野把玻璃杯放在桌沿。杯底碰到木板时发出轻轻一响，他抬眼看向林默，示意他先坐下。",
    ]
    scene_templates = [
        "林默坐在长椅边缘，膝盖没有完全放松。检测中心的空气带着消毒水的味道，风从排气口吹下来，掠过他后颈时有些冷。",
        "陈野翻开登记簿，笔尖停在姓名栏上。他没有催促，只把旁边的旧印章推近一点，让林默自己看清流程。",
        "旁边的年轻女人抱着档案袋，指节因为用力而发白。她几次想说话，最后都把声音咽了回去，只剩纸袋轻轻摩擦。",
        "林默写下名字，最后一笔顿得很重。他知道这只是普通登记，可那行黑字落下去，像是把自己推进了一条看不见的线。",
        "陈野接过表格，视线在编号上停了一瞬。他把表格压进文件夹，动作很稳，却没有立刻合上。",
        "走廊尽头有人咳了一声，队伍往前挪了半步。林默跟着站起，又停下，等陈野把临时牌递过来。",
        "临时牌是灰色的，边角磨得发亮。林默把它挂在胸前，塑料壳贴着衣服，像一块不属于他的重量。",
        "陈野说登记完成后要去三号室复核。林默点头，问复核要多久，陈野只说看情况。",
        "三号室的椅子比外面更硬。林默坐下时，头顶灯管闪了两下，白光在桌面上跳出一小片影子。",
        "记录员把问题念得很慢，每一句都像重复过很多遍。林默按要求回答，声音保持平稳，掌心却一直贴着裤缝。",
        "他想起早上出门前，母亲把早餐放在门口，没有问太多。那份沉默比追问更重，让他一路都没有回头。",
        "复核结束时，记录员让他在底栏签字。林默握笔的手停了一下，还是把名字写完整。",
        "陈野在门外等他，手里多了一张蓝色通知单。他把纸递过来，说今天不用再排队，下午直接去东侧楼。",
        "林默看着通知单上的时间，问是不是每个人都有这一步。陈野没有立刻回答，只把登记簿夹在胳膊下。",
        "窗外的天色沉了些，玻璃上浮着城市灰白的倒影。林默把通知单折好，放进口袋最里层。",
        "他们沿着走廊往外走，脚步声一前一后。林默没有再问，陈野也没有解释，只在转角处放慢了一点。",
        "出口旁的公告栏贴着新的名单，纸边还没有卷起。林默从旁边经过，目光扫过那些陌生名字，最后停在自己的编号上。",
        "编号后面没有备注，只有一个空白的方格。林默盯了两秒，把视线移开，继续往门口走。",
        "陈野把门禁卡贴上读卡器，绿灯亮起。门开的时候，外面的风涌进来，带着雨前潮湿的气味。",
        "林默跨过门槛，忽然觉得胸前的临时牌轻轻晃了一下。他按住它，抬头看向东侧楼的方向。",
        "东侧楼比主楼矮一层，窗户全都拉着灰色百叶。林默站在台阶下，确认通知单上的时间还早。",
        "陈野说可以先去食堂等。林默摇头，说自己想在外面走走，陈野看了他一眼，没有阻拦。",
        "他沿着院墙慢慢往前，雨云压在楼顶上。路边积着昨夜的水，倒影被风吹得一层层散开。",
        "林默停在一棵梧桐树下，拿出通知单又看了一遍。纸面很薄，字却像印得太深，怎么折都留着痕。",
        "午后的铃声从主楼里传出来，队伍重新排起。林默把通知单收好，转身朝东侧楼走去。",
        "东侧楼门口没有排队的人，只有一名保安坐在玻璃岗亭里。林默把临时牌贴近窗口，对方看了编号，按下桌边的开关。",
        "铁门缓缓打开，轴承拖出低低的摩擦声。林默走进去时，脚下地砖比主楼干净，干净得让人不太愿意踩重。",
        "楼道两侧挂着旧照片，照片里的员工穿着同样的制服，笑容被时间洗得很淡。林默没有停，只用余光扫过那些脸。",
        "二楼的指示牌指向复测区。林默沿着箭头上楼，手指一直贴在口袋边缘，确认通知单还在那里。",
        "楼梯转角处有一面窄窗，窗外的院子被分成灰绿两块。陈野没有跟上来，林默第一次清楚地意识到，接下来的流程只能自己走完。",
        "复测区门前铺着一条旧地毯，边缘已经翘起。林默停在门外，整理了一下衣领，又把临时牌扶正。",
        "他抬手敲了敲门，力道不轻不重。里面隔了几秒才有人回应，让他进去。",
        "房间里只有一张长桌和两把椅子。桌面上摆着空白记录纸，纸角压着一支黑色签字笔。",
        "林默坐到指定的位置，背脊没有靠上椅背。他把通知单放在桌上，等对面的人开口。",
        "对方翻看编号时没有表情，只问他上午有没有离开中心。林默说没有，只在院墙边走了一圈。",
        "笔尖在纸上划过，留下细细的沙沙声。林默听着那声音，觉得时间被分成很多短而硬的段落。",
    ]
    paragraphs.extend(scene_templates)
    filler_templates = [
        "墙角的钟走得很慢，秒针每跳一下，都像在提醒他不要提前给任何事下判断。林默把呼吸压平，继续等下一句指令。",
        "桌上的记录纸被灯照得发白，边缘有细小的毛刺。林默看着那些毛刺，想起自己早上撕开信封时留下的纸屑。",
        "对面的人没有抬头，只把问题按顺序念下去。林默回答得很短，尽量让每个字都落在该落的位置。",
        "空气里没有明显的味道，安静却压得人肩膀发紧。林默听见自己的袖口擦过桌边，声音轻得几乎不存在。",
        "他知道流程还没有结束，也知道现在追问不会得到更多答案。于是他把视线放回通知单，等着下一枚章盖下来。",
    ]
    index = 0
    while build_mechanical_context(1, "\n\n".join(paragraphs)).chinese_chars < 2050:
        paragraphs.append(filler_templates[index % len(filler_templates)])
        index += 1
    text = "\n\n".join(paragraphs)
    if build_mechanical_context(1, text).chinese_chars < 2000:
        raise RuntimeError("prototype chapter text is shorter than 2000 Chinese chars")
    return text


if __name__ == "__main__":
    raise SystemExit(main())
