from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from utils.autocomplete import user_autocomplete


def _run(coro):
    return asyncio.run(coro)


def _member(*, user_id: int, name: str, display_name: str, bot: bool = False):
    member = MagicMock()
    member.id = user_id
    member.name = name
    member.display_name = display_name
    member.bot = bot
    return member


def test_user_autocomplete_caps_empty_query_without_mongo() -> None:
    members = [_member(user_id=i, name=f"u{i}", display_name=f"User {i}") for i in range(40)]
    members.append(_member(user_id=99, name="bot", display_name="Bot", bot=True))
    guild = MagicMock()
    guild.members = members
    guild.get_member = MagicMock()
    interaction = MagicMock()
    interaction.guild = guild

    with (
        patch("utils.autocomplete.get_context", return_value=SimpleNamespace()),
        patch("database.users.UserRepo") as repo_cls,
    ):
        choices = _run(user_autocomplete(interaction, ""))

    assert len(choices) == 25
    assert all(choice.value != "99" for choice in choices)
    repo_cls.assert_not_called()


def test_user_autocomplete_filters_by_name() -> None:
    rio = _member(user_id=7, name="rio", display_name="Rio")
    other = _member(user_id=8, name="sam", display_name="Sam")
    guild = MagicMock()
    guild.members = [rio, other]
    guild.get_member = lambda uid: rio if uid == 7 else None
    interaction = MagicMock()
    interaction.guild = guild

    with patch("utils.autocomplete.get_context", return_value=SimpleNamespace()):
        choices = _run(user_autocomplete(interaction, "ri"))

    assert [choice.value for choice in choices] == ["7"]
