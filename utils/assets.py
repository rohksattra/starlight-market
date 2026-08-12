"""GitHub raw URLs for per-game marketplace assets."""
from __future__ import annotations

from urllib.parse import quote

from core.tenant import GameContext


def _repo_file_base(ctx: GameContext) -> str:
    assets = ctx.assets
    if not assets.github_user or not assets.github_repo or not assets.base_path:
        return ""
    root = assets.base_path.strip("/")
    return (
        f"https://github.com/{assets.github_user}/{assets.github_repo}"
        f"/raw/refs/heads/{assets.github_branch}/{root}"
    )


def _seg(value: str) -> str:
    return quote(value, safe="")


def item_image_url(ctx: GameContext, *, item_image: str, item_category: str) -> str:
    if not item_image or not item_category:
        return ""
    base = _repo_file_base(ctx)
    if not base:
        return ""
    return f"{base}/items/{_seg(item_category)}/{_seg(item_image)}"


def monster_image_url(ctx: GameContext, *, monster_image: str) -> str:
    if not monster_image:
        return ""
    base = _repo_file_base(ctx)
    if not base:
        return ""
    return f"{base}/monsters/{_seg(monster_image)}"
