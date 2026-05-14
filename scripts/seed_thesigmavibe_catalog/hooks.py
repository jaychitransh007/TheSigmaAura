"""Lede hooks per garment subtype. Deterministic pick: hash(product_id) % len.

Hand-written for the top subtypes that cover ~95% of TheSigmaVibe's 14,242
rows. Long-tail subtypes fall back to a generic per-category hook.

Voice: aspirational + playful, no cheekiness, no slang that ages.
"""

# Subtype → list of hook phrases. Each hook ends with a period.
# The generator picks one deterministically per product_id.
HOOKS: dict[str, list[str]] = {
    # Western tops
    "shirt": [
        "A shirt built to do everything.",
        "Crisp lines, easy attitude — the kind of shirt you reach for on repeat.",
        "Sharp enough for the office, easy enough for everywhere else.",
        "Your new go-to shirt.",
        "The shirt that handles every kind of day.",
    ],
    "tshirt": [
        "An everyday t-shirt with quiet confidence.",
        "Soft, easy, and ready for anything.",
        "The kind of t-shirt that finds its way into the rotation fast.",
        "Wear it solo, layer it under, take it anywhere.",
        "The t-shirt you'll actually want to wear.",
    ],
    "blouse": [
        "A blouse with quiet polish.",
        "Cut to flatter, made to move with you.",
        "The blouse that makes the rest of the outfit work harder.",
        "A blouse that's equally at home dressed up or down.",
    ],
    "sweater": [
        "Cozy, considered, ready for cooler days.",
        "A sweater that does soft, structured, and stylish all at once.",
        "Made to layer, designed to last.",
        "Your new favorite knit.",
    ],
    "sweatshirt": [
        "Off-duty energy, on-trend cut.",
        "A sweatshirt that works as hard as you do.",
        "Easy, soft, and ready for any low-key day.",
    ],
    "hoodie": [
        "A hoodie made for the long days.",
        "Soft, easy, and ready to go anywhere.",
        "Your new everyday hoodie.",
    ],

    # Western bottoms
    "jeans": [
        "Jeans designed to feel like a second skin.",
        "Denim that fits, holds, and moves with you.",
        "Your new everyday jean.",
        "The jeans you'll keep coming back to.",
    ],
    "trouser": [
        "Trousers that move from desk to dinner without missing a beat.",
        "Cut clean, made to move.",
        "Workwear that doesn't feel like workwear.",
        "Your new go-to trouser.",
    ],
    "shorts": [
        "Shorts built for the heat and the moments.",
        "Easy, cool, ready to go.",
    ],
    "track_pants": [
        "Built for movement, made for everything in between.",
        "Easy track pants for easy days.",
    ],
    "palazzo": [
        "Palazzos with breezy, fluid energy.",
        "Wide-leg ease that moves with you.",
    ],
    "skirt": [
        "A skirt that swings between dressed-up and dressed-down.",
        "Easy lines, real movement.",
    ],
    "leggings": [
        "Leggings that hold their shape and stretch where they need to.",
        "Soft, smooth, ready for layering.",
    ],

    # Western outerwear
    "jacket": [
        "A jacket that finishes the outfit and starts the conversation.",
        "Layer up without losing the silhouette.",
        "The jacket that earns its keep.",
        "Built for the in-between days.",
    ],
    "blazer": [
        "A blazer that sharpens every outfit it touches.",
        "Tailored polish, easy attitude.",
        "Cut to elevate — wear it your way.",
        "The blazer that does formal and casual equally well.",
    ],
    "coat": [
        "A coat that brings warmth and presence in equal measure.",
        "Made to layer, designed to last.",
    ],
    "shacket": [
        "Half shirt, half jacket, fully versatile.",
        "Layer it on, take it off — built for in-between weather.",
    ],
    "cardigan": [
        "Soft, structured, ready to layer.",
        "A cardigan that goes with everything you own.",
    ],
    "shrug": [
        "A shrug that adds just enough cover.",
        "Easy layering for any moment.",
    ],

    # Dresses / one-piece Western
    "dress": [
        "A dress designed for the moments you want to remember.",
        "Easy to throw on, hard to take off.",
        "A dress that does the work for you.",
        "Cut to flatter, made to move.",
        "Your new effortless win.",
    ],
    "gown": [
        "A gown built for the big moments.",
        "Cut to make an entrance.",
        "The kind of gown that turns a room.",
    ],
    "jumpsuit": [
        "One piece, full impact.",
        "A jumpsuit that does the work of a full outfit on its own.",
    ],
    "playsuit": [
        "Easy, playful, ready to go.",
    ],

    # Ethnic — sarees
    "saree": [
        "A saree built for the moments worth remembering.",
        "Drape, shine, and presence in one piece.",
        "A saree that catches every light in the room.",
        "Tradition with modern energy.",
        "The kind of drape that quiets the room.",
    ],

    # Ethnic — sets
    "salwar_set": [
        "A salwar set that brings the whole look together.",
        "Festive ease, ready out of the box.",
        "Three pieces, one full mood.",
        "A coordinated set that does the styling for you.",
    ],
    "kurta_set": [
        "A kurta set that handles every kind of occasion.",
        "Three pieces, fully sorted.",
        "Easy festive energy in one set.",
        "The set that takes the guesswork out.",
    ],
    "salwar_suit": [
        "A salwar suit that brings traditional polish.",
        "Festive ready, beautifully made.",
    ],
    "suit_set": [
        "A suit set with festive presence.",
        "Polished, coordinated, ready to go.",
    ],
    "lehenga_set": [
        "A lehenga set built for the celebration moments.",
        "Showstopping volume, considered detail.",
        "The kind of lehenga that earns its place in the photos.",
    ],
    "ethnic_set": [
        "A coordinated ethnic set that does the work for you.",
        "Festive ready, fully styled.",
    ],
    "co_ord_set": [
        "Matched pieces that do half the styling work.",
        "Coordinated easy, polished finish.",
        "A co-ord set for the days you want effortless.",
    ],

    # Ethnic — single garments
    "anarkali": [
        "An anarkali with sweep and structure in equal parts.",
        "Floor-grazing presence, beautifully cut.",
        "The kind of anarkali that earns the second look.",
    ],
    "kurta": [
        "A kurta that handles every kind of moment.",
        "Easy, polished, festive-ready.",
        "Traditional cut with modern energy.",
    ],
    "kurti": [
        "A kurti for everyday ease with festive polish.",
        "Easy to wear, beautifully made.",
        "The kurti that goes everywhere with you.",
    ],
    "tunic": [
        "A tunic that bridges easy and elevated.",
        "Cut to flatter, made to move.",
    ],
    "nehru_jacket": [
        "A nehru jacket that finishes the festive look.",
        "Tailored polish with traditional roots.",
    ],

    # Long-tail / fallback
    "kaftan": [
        "A kaftan with breezy, effortless energy.",
    ],
    "poncho": [
        "A poncho that layers ease over everything.",
    ],
    "dungarees": [
        "Dungarees with easy, playful attitude.",
    ],
    "tracksuit": [
        "Built for movement, made for comfort.",
    ],
}


# Per-category fallback hooks for subtypes without their own pool.
CATEGORY_FALLBACK: dict[str, list[str]] = {
    "top":       ["A top with quiet polish.", "Easy lines, real attitude."],
    "bottom":    ["Made to move, designed to last.", "Easy lines, easy attitude."],
    "one_piece": ["A one-and-done piece you'll keep coming back to.", "Easy to wear, hard to forget."],
    "outerwear": ["A layer that finishes the outfit.", "Built to layer, made to last."],
    "set":       ["A coordinated set that does the styling for you.", "Pieces that work together effortlessly."],
}


def pick_hook(product_id: str, subtype: str, category: str) -> str:
    """Pick a hook deterministically from the subtype pool, falling back
    to category, then to a universal generic hook."""
    pool = HOOKS.get(subtype) or CATEGORY_FALLBACK.get(category)
    if not pool:
        return "Easy to wear, made to last."
    # Stable hash via Python's built-in hash on bytes (deterministic per run
    # for a fixed PYTHONHASHSEED is NOT guaranteed — but we use sum of
    # ord(c) which is fully deterministic across runs).
    idx = sum(ord(c) for c in (product_id or "")) % len(pool)
    return pool[idx]
