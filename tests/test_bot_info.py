from __future__ import annotations

from models.bot_info import COMMAND_GROUPS


def test_member_commands_keep_prefix_and_slash() -> None:
    member = next(group for group in COMMAND_GROUPS if group["title"].startswith("👤"))
    names = [entry["name"] for entry in member["commands"]]
    assert names == ["!minfo", "!mme", "/profile", "/monster-grind"]
