"""Empire of Praxia item catalog (fill before enabling tenant).

Shape matches CoA:
  DEFAULT_ITEMS = {
    "Category Name": [
      {"item_name": "...", "item_price": 1000, "item_image": "...png", "item_emoji": "🌟"},
    ],
  }
"""

DEFAULT_ITEMS: dict[str, list[dict]] = {
    # Example (remove when real catalog is ready):
    # "Resources": [
    #     {"item_name": "Example Ore", "item_price": 1000, "item_image": "example-ore.png", "item_emoji": "🌟"},
    # ],
}
