"""Community embeds, buttons, and modals (UI only)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal

import discord
from discord import ui

from bot.ui.shared import ctx_from_guild, set_starlight_footer
from core.tenant import GameContext
from models.bot_info import COMMAND_GROUPS, CommandEntry, CommandGroup, bot_intro
from models.giveaway import Giveaway, giveaway_effective_status

EMBED_COLOR = 0xFFD700
MAX_DESCRIPTION = 4096
MAX_FIELD_VALUE = 1024
MAX_FIELDS = 25
MAX_EMBED_CHARS = 5500
WinnerSelectMode = Literal["reroll", "claim"]


def giveaway_custom_join(giveaway_id: str) -> str:
    return f"sl_gv:{giveaway_id}:j"


def giveaway_custom_participants(giveaway_id: str) -> str:
    return f"sl_gv:{giveaway_id}:p"


def giveaway_custom_refresh(giveaway_id: str) -> str:
    return f"sl_gv:{giveaway_id}:r"


def giveaway_custom_cancel(giveaway_id: str) -> str:
    return f"sl_gv:{giveaway_id}:c"


def giveaway_custom_reroll_all(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:ra"


def giveaway_custom_reroll_partial(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:rp"


def giveaway_custom_claim(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:cl"


def giveaway_custom_close(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:x"


def welcome_embed(member: discord.Member) -> discord.Embed:
    ctx = ctx_from_guild(member.guild)
    embed = discord.Embed(
        description=(
            f"Hello, {member.mention}!\n"
            f"👋 Welcome to **{member.guild.name}**!\n"
            "We're glad to have you here ✨"
        ),
        color=EMBED_COLOR,
    )
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def farewell_embed(member: discord.Member) -> discord.Embed:
    ctx = ctx_from_guild(member.guild)
    embed = discord.Embed(
        description=(
            f"**{member.mention}** has left the server.\n"
            "We wish you the best on your next journey 🚀"
        ),
        color=EMBED_COLOR,
    )
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def giveaway_panel_embed(*, doc: Giveaway, guild: discord.Guild | None) -> discord.Embed:
    host_id = doc.get("host_user_id", "")
    prize = str(doc.get("prize_description", ""))[:4096]
    winner_count = int(doc.get("winner_count", 1))
    ends_at = doc.get("ends_at")
    if not isinstance(ends_at, datetime):
        ends_at = datetime.utcnow()

    status = giveaway_effective_status(doc)
    pids: List[str] = list(doc.get("participant_user_ids") or [])
    participant_count = len(pids)

    host_mention = f"- <@{host_id}>" if host_id.isdigit() else "—"
    if guild and host_id.isdigit():
        m = guild.get_member(int(host_id))
        if m:
            host_mention = m.mention

    if status == "open":
        status_line = "🟢 **Open** — use **Join** to enter."
    elif status == "ended":
        status_line = "🔒 **Closed** — drawing winners…"
    elif status == "completed":
        status_line = "✅ **Completed** — winners announced below."
    elif status == "closed":
        status_line = "🔒 **Closed** — all rewards collected."
    elif status == "cancelled":
        status_line = "⛔ **Cancelled**."
    else:
        status_line = "—"

    embed = discord.Embed(
        title="🎁 Giveaway",
        description=prize or "—",
        color=EMBED_COLOR,
    )
    embed.add_field(name="Host", value=host_mention, inline=True)
    embed.add_field(name="Winners", value=f"**{winner_count}**", inline=True)
    embed.add_field(name="Participants", value=f"**{participant_count}**", inline=True)
    embed.add_field(name="Ends", value=discord.utils.format_dt(ends_at, style="F"), inline=False)
    embed.add_field(name="Status", value=status_line, inline=False)
    set_starlight_footer(embed, ctx=ctx_from_guild(guild))
    return embed


def giveaway_winners_embed(
    *,
    doc: Giveaway,
    guild: discord.Guild | None,
    winner_user_ids: List[str],
    bank_manager_role_id: int = 0,
) -> discord.Embed:
    prize = str(doc.get("prize_description", ""))[:4096]
    host_id = str(doc.get("host_user_id", ""))

    host_mention = f"- <@{host_id}>" if host_id.isdigit() else "—"
    if guild and host_id.isdigit():
        m = guild.get_member(int(host_id))
        if m:
            host_mention = m.mention

    claimed_ids = set(str(uid) for uid in doc.get("claimed_winner_user_ids") or [])

    if winner_user_ids:
        lines = []
        for i, uid in enumerate(winner_user_ids, start=1):
            mention = f"<@{uid}>"
            if guild:
                mem = guild.get_member(int(uid))
                if mem:
                    mention = mem.mention
            claimed_mark = " ✅" if str(uid) in claimed_ids else ""
            lines.append(f"**{i}.** {mention}{claimed_mark}")
        winners_block = "\n".join(lines)
    else:
        winners_block = "*No entries — no winners.*"

    embed = discord.Embed(
        title="🎁 Giveaway Winners",
        description=prize or "—",
        color=EMBED_COLOR,
    )
    embed.add_field(name="Host", value=host_mention, inline=True)
    embed.add_field(name="Winners", value=winners_block, inline=False)

    status = giveaway_effective_status(doc)
    if status == "closed":
        embed.add_field(
            name="Status",
            value="🔒 Giveaway closed. All rewards have been collected.",
            inline=False,
        )
    elif status == "cancelled":
        embed.add_field(
            name="Status",
            value="⛔ Giveaway cancelled.",
            inline=False,
        )

    reroll_count = int(doc.get("reroll_count", 0) or 0)
    last_rerolled_by = str(doc.get("last_rerolled_by", "") or "")
    last_rerolled_at = doc.get("last_rerolled_at")

    if reroll_count > 0:
        reroll_line = f"🔄 Rerolled **{reroll_count}** time(s)."
        if last_rerolled_by.isdigit():
            reroll_line += f"\nLast rerolled by <@{last_rerolled_by}>."
        if isinstance(last_rerolled_at, datetime):
            reroll_line += f"\nAt {discord.utils.format_dt(last_rerolled_at, style='F')}."
        embed.add_field(name="Reroll Info", value=reroll_line, inline=False)

    if status not in ("closed", "cancelled") and bank_manager_role_id:
        embed.add_field(
            name="Reward",
            value=f"Please ping <@&{bank_manager_role_id}> to collect your reward.",
            inline=False,
        )

    set_starlight_footer(embed, ctx=ctx_from_guild(guild))
    return embed


def _embed_char_count(embed: discord.Embed) -> int:
    total = len(embed.title or "") + len(embed.description or "")
    if embed.footer and embed.footer.text:
        total += len(embed.footer.text)
    for field in embed.fields:
        total += len(field.name) + len(field.value)
    return total


def _new_slinfo_embed(
    *,
    title: str,
    ctx: GameContext | None = None,
    description: str | None = None,
    bot_user: discord.ClientUser | discord.User | None = None,
    with_thumbnail: bool = False,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR,
    )
    if with_thumbnail and bot_user is not None:
        embed.set_thumbnail(url=bot_user.display_avatar.url)
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return embed


def _can_add_field(embed: discord.Embed, *, name: str, value: str) -> bool:
    if len(embed.fields) >= MAX_FIELDS:
        return False
    if len(value) > MAX_FIELD_VALUE:
        return False
    projected = _embed_char_count(embed) + len(name) + len(value)
    return projected <= MAX_EMBED_CHARS


def _chunk_command_value(commands: list[CommandEntry]) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for entry in commands:
        line = f"`{entry['name']}` — {entry['description']}"
        extra = len(line) + (1 if current else 0)
        if current and current_len + extra > MAX_FIELD_VALUE:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += extra

    if current:
        chunks.append("\n".join(current))
    return chunks


def _add_group_fields(
    embeds: list[discord.Embed],
    group: CommandGroup,
    *,
    page_title: str,
    ctx: GameContext | None = None,
) -> None:
    chunks = _chunk_command_value(group["commands"])
    for index, value in enumerate(chunks):
        name = group["title"] if index == 0 else f"{group['title']} (cont.)"
        if not embeds or not _can_add_field(embeds[-1], name=name, value=value):
            embeds.append(_new_slinfo_embed(title=page_title, ctx=ctx))
        embeds[-1].add_field(name=name, value=value, inline=False)


def slinfo_embeds(
    *,
    ctx: GameContext,
    bot_user: discord.ClientUser | discord.User | None = None,
) -> list[discord.Embed]:
    intro_text = bot_intro(
        market_name=ctx.brand.name,
        audience=ctx.brand.audience,
        emoji=ctx.brand.emoji,
    )
    intro = intro_text if len(intro_text) <= MAX_DESCRIPTION else intro_text[: MAX_DESCRIPTION - 1] + "…"
    brand = ctx.brand_label
    embeds: list[discord.Embed] = [
        _new_slinfo_embed(
            title=f"{brand} — Bot Info",
            description=intro,
            bot_user=bot_user,
            with_thumbnail=True,
            ctx=ctx,
        )
    ]

    for group in COMMAND_GROUPS:
        _add_group_fields(embeds, group, page_title=f"{brand} — Commands", ctx=ctx)

    if len(embeds) > 1:
        total = len(embeds)
        for index, embed in enumerate(embeds, start=1):
            set_starlight_footer(
                embed,
                ctx=ctx,
                detail=f"Page {index}/{total}",
                include_button_notice=False,
            )

    return embeds


class GiveawayView(ui.View):
    def __init__(
        self,
        giveaway_id: str,
        *,
        join_disabled: bool = False,
        refresh_disabled: bool = False,
        cancel_disabled: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

        join_btn = ui.Button(
            label="Join",
            style=discord.ButtonStyle.success,
            custom_id=giveaway_custom_join(giveaway_id),
            disabled=join_disabled,
            row=0,
        )
        join_btn.callback = self._on_join
        self.add_item(join_btn)

        part_btn = ui.Button(
            label="Participants",
            style=discord.ButtonStyle.primary,
            custom_id=giveaway_custom_participants(giveaway_id),
            row=0,
        )
        part_btn.callback = self._on_participants
        self.add_item(part_btn)

        ref_btn = ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id=giveaway_custom_refresh(giveaway_id),
            disabled=refresh_disabled,
            row=0,
        )
        ref_btn.callback = self._on_refresh
        self.add_item(ref_btn)

        cancel_btn = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id=giveaway_custom_cancel(giveaway_id),
            disabled=cancel_disabled,
            row=0,
        )
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    async def _on_join(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        await get_community_handler().handle_join(interaction, self.giveaway_id)

    async def _on_participants(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        await get_community_handler().handle_participants(interaction, self.giveaway_id)

    async def _on_refresh(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        await get_community_handler().handle_refresh(interaction, self.giveaway_id)

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        await get_community_handler().handle_cancel_giveaway(interaction, self.giveaway_id)


class GiveawayWinnerView(ui.View):
    def __init__(self, giveaway_id: str, *, disabled: bool = False) -> None:
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

        reroll_all = ui.Button(
            label="Reroll All",
            style=discord.ButtonStyle.secondary,
            custom_id=giveaway_custom_reroll_all(giveaway_id),
            disabled=disabled,
            row=0,
        )
        reroll_all.callback = self._on_reroll_all
        self.add_item(reroll_all)

        reroll_partial = ui.Button(
            label="Reroll Partial",
            style=discord.ButtonStyle.secondary,
            custom_id=giveaway_custom_reroll_partial(giveaway_id),
            disabled=disabled,
            row=0,
        )
        reroll_partial.callback = self._on_reroll_partial
        self.add_item(reroll_partial)

        claim_btn = ui.Button(
            label="Claimed",
            style=discord.ButtonStyle.success,
            custom_id=giveaway_custom_claim(giveaway_id),
            disabled=disabled,
            row=0,
        )
        claim_btn.callback = self._on_claim
        self.add_item(claim_btn)

        close_btn = ui.Button(
            label="Close",
            style=discord.ButtonStyle.danger,
            custom_id=giveaway_custom_close(giveaway_id),
            disabled=disabled,
            row=0,
        )
        close_btn.callback = self._on_close
        self.add_item(close_btn)

    async def _on_reroll_all(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        await get_community_handler().handle_reroll_all(interaction, self.giveaway_id)

    async def _on_reroll_partial(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        await get_community_handler().handle_reroll_partial_prompt(interaction, self.giveaway_id)

    async def _on_claim(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        await get_community_handler().handle_mark_claimed_prompt(interaction, self.giveaway_id)

    async def _on_close(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        await get_community_handler().handle_close_giveaway(interaction, self.giveaway_id)


class GiveawayWinnerSelect(ui.Select):
    def __init__(
        self,
        giveaway_id: str,
        winner_user_ids: List[str],
        guild: discord.Guild | None,
        *,
        mode: WinnerSelectMode,
    ) -> None:
        self.giveaway_id = giveaway_id
        self.mode = mode

        options: List[discord.SelectOption] = []
        for i, uid in enumerate(winner_user_ids[:25], start=1):
            label = f"Winner {i}"
            if guild:
                member = guild.get_member(int(uid))
                if member:
                    label = member.display_name[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=uid,
                    description=f"Winner slot #{i}",
                )
            )

        super().__init__(
            placeholder="Choose winner(s)",
            min_values=1,
            max_values=max(1, len(options)),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from bot.handlers.community import get_community_handler

        handler = get_community_handler()
        if self.mode == "claim":
            await handler.handle_mark_claimed_selected(
                interaction,
                self.giveaway_id,
                list(self.values),
            )
            return
        await handler.handle_reroll_partial_selected(
            interaction,
            self.giveaway_id,
            list(self.values),
        )


class GiveawayWinnerSelectView(ui.View):
    def __init__(
        self,
        giveaway_id: str,
        winner_user_ids: List[str],
        guild: discord.Guild | None,
        *,
        mode: WinnerSelectMode,
    ) -> None:
        super().__init__(timeout=120)
        self.add_item(
            GiveawayWinnerSelect(
                giveaway_id,
                winner_user_ids,
                guild,
                mode=mode,
            )
        )
