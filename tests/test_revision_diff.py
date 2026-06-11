from __future__ import annotations

from storyforge3.audit.revision_diff import build_revision_diff


def test_build_revision_diff_reports_replace_block() -> None:
    diff = build_revision_diff("第一段旧稿。\n\n第二段保留。", "第一段新稿。\n\n第二段保留。")

    assert diff.unit == "paragraph"
    assert diff.summary.changed_blocks == 1
    assert diff.summary.added_blocks == 0
    assert diff.summary.removed_blocks == 0
    assert diff.blocks == (
        type(diff.blocks[0])(
            kind="replace",
            before_text="第一段旧稿。",
            after_text="第一段新稿。",
        ),
    )


def test_build_revision_diff_reports_insert_and_delete_blocks() -> None:
    diff = build_revision_diff("第一段保留。\n\n第二段删除。", "第一段保留。\n\n新增段落。")

    assert diff.summary.changed_blocks == 1
    assert diff.summary.added_blocks == 0
    assert diff.summary.removed_blocks == 0
    assert tuple(block.kind for block in diff.blocks) == ("replace",)
    assert diff.blocks[0].before_text == "第二段删除。"
    assert diff.blocks[0].after_text == "新增段落。"


def test_build_revision_diff_skips_equal_blocks_for_noop() -> None:
    diff = build_revision_diff("林默站在门口。", "林默站在门口。")

    assert diff.summary.changed_blocks == 0
    assert diff.summary.added_blocks == 0
    assert diff.summary.removed_blocks == 0
    assert diff.blocks == ()
