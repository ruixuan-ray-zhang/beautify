"""What each Pantone book is for: intended use and physical medium.

pantone-cli indexes carry this per book (`books[].info.en`); for color book files
(.acb / .aco / .ase) it is looked up here from the book's name. The same input color
maps to different codes in different books, so a paper picks one book on purpose.
"""

from __future__ import annotations

import re

# (pattern on the lower-cased name, pantone-cli book id, target use, medium, note for papers)
# More specific patterns first: "color bridge coated" also contains "coated".
_KNOWN = (
    (r"color ?bridge.*uncoated", "pantoneColorBridgeUncoated", "Spot vs process evaluation",
     "Spot color and process ink on uncoated paper", ""),
    (r"color ?bridge", "pantoneColorBridgeCoated", "Spot vs process evaluation",
     "Spot color and process ink on coated paper", ""),
    (r"cmyk.*uncoated", "pantoneCmykUncoated", "Graphic design",
     "CMYK process ink on uncoated paper", ""),
    (r"cmyk", "pantoneCmykCoated", "Graphic design", "CMYK process ink on coated paper", ""),
    (r"metallic", "pantoneMetallicsCoated", "Graphic design", "Metallic spot ink on coated paper",
     "metallic sheen cannot be shown on screen or in a PDF"),
    (r"pastel|neon", "pantonePastelsNeonsCoated", "Graphic design",
     "Pastel and fluorescent spot ink", "fluorescent colors lie far outside sRGB"),
    (r"solid.*uncoated|\buncoated\b|(?<![a-z])u$", "pantoneSolidUncoated", "Graphic design",
     "Spot color ink on uncoated paper", ""),
    (r"solid.*coated|\bcoated\b|(?<![a-z])c$", "pantoneSolidCoated", "Graphic design",
     "Spot color ink on coated paper", ""),
    (r"\btcx\b|cotton", "pantoneFhCottonTcx", "Fashion, textiles, soft home", "Dye on cotton fabric", ""),
    (r"\btsx\b|polyester", "pantoneFhiPolyesterTsx", "Fashion, activewear", "Dye on polyester fabric", ""),
    (r"\btpg\b|\btpx\b|fhi.*paper", "pantoneFhiPaperTpg", "Product design", "Lacquer coating on paper", ""),
    (r"skin ?tone", "pantoneSkinToneGuide", "Skin tone reference", "SkinTone guide", ""),
)


def describe(name: str) -> dict | None:
    """Book name -> {id, target, medium, note}, or None for an unknown book."""
    low = " ".join(name.replace("®", " ").replace("-", " ").lower().split())
    low = re.sub(r"\s*v\d+$", "", low)                 # "... coated v5" edition suffix
    for pattern, book_id, target, medium, note in _KNOWN:
        if re.search(pattern, low):
            return {"id": book_id, "target": target, "medium": medium, "note": note}
    return None


def from_pantone_cli(summary: dict) -> dict:
    """pantone-cli BookSummary -> the same shape as describe()."""
    info = (summary.get("info") or {}).get("en") or {}
    known = describe(summary.get("title") or summary.get("id", "")) or {}
    return {"id": summary.get("id", ""), "target": info.get("target") or known.get("target", ""),
            "medium": info.get("description") or known.get("medium", ""),
            "group": summary.get("group") or info.get("group", ""), "note": known.get("note", "")}
