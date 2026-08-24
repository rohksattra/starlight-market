"""Static bot intro and command catalog for !minfo."""
from __future__ import annotations

from typing import Final, TypedDict


class CommandEntry(TypedDict):
    name: str
    description: str


class CommandGroup(TypedDict):
    title: str
    commands: list[CommandEntry]


def bot_intro(*, market_name: str, audience: str, emoji: str) -> str:
    return (
        f"## Hello, {audience}! 👋\n"
        "Are you tired of grinding and wasting time shouting in chat just to find items?\n"
        f"Come to ***{market_name}*** ✨ — place an order and become our ***Customer***!\n\n"
        "Do you love grinding, farming, or selling the items you get to earn gold?\n"
        f"Come to ***{market_name}*** 💰 — take an order and become our ***Worker***!\n\n"
        f"🌌 What is ***{market_name}***?\n"
        f"{market_name} is a player-driven ***marketplace*** where ***customers*** can safely "
        "***place orders*** and ***workers complete them*** for gold.\n\n"
        f"### {emoji} Features\n"
        "🤖 ***Automated***, bot-based order system for customers\n"
        "💸 Only 1% gold commission per completed order — ***workers keep 99% gold***\n"
        "🛒 Competitive prices and ***great deals*** for everyone\n"
        "♾️ ***Unlimited*** item ***quantities*** — anytime, anything\n"
        "📩 ***Custom orders*** available\n"
        "🌍 ***Safe, friendly, and great environment***\n"
        "🛡️ ***Trusted*** by the community — including mods and guards\n"
        "✨ And much more!"
    )

COMMAND_GROUPS: Final[list[CommandGroup]] = [
    {
        "title": "👤 Member",
        "commands": [
            {"name": "!minfo", "description": "Bot info and available commands"},
            {"name": "!mme", "description": "View your profile"},
            {"name": "/profile", "description": "View a member profile"},
        ],
    },
    {
        "title": "🛡️ Moderator (+ 👤 Member)",
        "commands": [
            {"name": "/delete-message", "description": "Delete recent channel messages"},
        ],
    },
    {
        "title": "🏦 Bank Manager (+ 👤 Member)",
        "commands": [
            {"name": "!mcancel", "description": "Cancel the current order channel"},
            {"name": "/custom-order", "description": "Create a custom/manual order"},
            {"name": "/order-item-price-update", "description": "Update order item price"},
            {"name": "/order-item-quantity-update", "description": "Set, add, or reduce order quantity"},
            {"name": "/order-customer-update", "description": "Change order customer"},
            {"name": "/force-claim", "description": "Force claim to a worker"},
            {"name": "/force-unclaim", "description": "Force unclaim a worker"},
            {"name": "/donation", "description": "Record a donation"},
            {"name": "/giveaway", "description": "Post a giveaway"},
            {"name": "/income", "description": "Record worker income or customer payment"},
            {"name": "/paid", "description": "Add manual worker income"},
            {"name": "/spent", "description": "Add manual customer spending"},
        ],
    },
    {
        "title": "💻 Bot Developer (all commands)",
        "commands": [
            {"name": "!morder", "description": "Post order entry panel"},
            {"name": "!mprice", "description": "Post price list panels"},
            {"name": "!mroles", "description": "Post role claim panel"},
            {"name": "!mrules", "description": "Post market rules panel"},
            {"name": "!mpickup", "description": "Post worker pickup guide"},
            {"name": "!mstat", "description": "Post market statistics"},
            {"name": "!mclaimable", "description": "List claimable order items"},
            {"name": "!mcleanupdata", "description": "Delete old orders, transactions, ratings"},
            {"name": "/leaderboard-panel", "description": "Post a leaderboard panel"},
            {"name": "/game-panel", "description": "Post a game panel"},
            {"name": "/update-category-name", "description": "Update item category name"},
            {"name": "/update-item-name", "description": "Update item name"},
            {"name": "/update-item-price", "description": "Update item price (0 = Unavailable)"},
            {"name": "/sync-member-role", "description": "Resync member tier roles"},
        ],
    },
]
