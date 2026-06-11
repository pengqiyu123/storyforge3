from __future__ import annotations

import difflib

from storyforge3.audit.chinese_text import count_chinese_chars, split_paragraphs
from storyforge3.models import RevisionDiff, RevisionDiffBlock, RevisionDiffSummary


def build_revision_diff(before_text: str, after_text: str) -> RevisionDiff:
    before_paragraphs = split_paragraphs(before_text)
    after_paragraphs = split_paragraphs(after_text)
    matcher = difflib.SequenceMatcher(a=before_paragraphs, b=after_paragraphs)

    blocks: list[RevisionDiffBlock] = []
    changed_blocks = 0
    added_blocks = 0
    removed_blocks = 0

    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode == "equal":
            continue
        if opcode == "replace":
            blocks.append(
                RevisionDiffBlock(
                    kind="replace",
                    before_text="\n\n".join(before_paragraphs[i1:i2]),
                    after_text="\n\n".join(after_paragraphs[j1:j2]),
                )
            )
            changed_blocks += 1
            continue
        if opcode == "insert":
            blocks.append(
                RevisionDiffBlock(
                    kind="insert",
                    after_text="\n\n".join(after_paragraphs[j1:j2]),
                )
            )
            added_blocks += 1
            continue
        if opcode == "delete":
            blocks.append(
                RevisionDiffBlock(
                    kind="delete",
                    before_text="\n\n".join(before_paragraphs[i1:i2]),
                )
            )
            removed_blocks += 1

    return RevisionDiff(
        unit="paragraph",
        summary=RevisionDiffSummary(
            changed_blocks=changed_blocks,
            added_blocks=added_blocks,
            removed_blocks=removed_blocks,
            before_chars=count_chinese_chars(before_text),
            after_chars=count_chinese_chars(after_text),
        ),
        blocks=tuple(blocks),
    )
