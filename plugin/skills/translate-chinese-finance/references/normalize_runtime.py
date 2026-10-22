"""Apply reviewed public translation corrections after upstream regeneration.

The upstream Chinese config generator is outside this repository. This
idempotent migration keeps its runtime snapshots consistent with the skill.
Run this file from any directory; paths resolve relative to the skill.
"""
from pathlib import Path
import re


def normalize(content: str, traditional: bool = False) -> str:
    fixes = ({"股價現金流比": "股價自由現金流比"} if traditional else
             {"市现率": "股价自由现金流比率", "股本回报率": "净资产收益率"})
    for wrong, correct in fixes.items():
        content = content.replace(wrong, correct)
    # A string replacement table cannot perform magnitude arithmetic.
    for section in ("NUMBER_UNITS", "CURRENCY_FORMAT_STANDARDS"):
        match = re.search(rf"(?ms)^## {section}\n(.*?)(?=^## |\Z)", content)
        if match:
            body = match.group(1)
            for key, value in (("B", "B"), ("M", "M"), ("K", "K"), ("T", "T"),
                               ("standard_billion", "billion"),
                               ("standard_million", "million"),
                               ("standard_thousand", "thousand")):
                body = re.sub(rf"(?m)^\| {key} \| [^|]+\|$", f"| {key} | {value} |", body)
            content = content[:match.start(1)] + body + content[match.end(1):]
    match = re.search(r"(?ms)^## SCORE_LABEL_FIXES\n(.*?)(?=^## |\Z)", content)
    if match:
        body = re.sub(r"(?m)^\| ([^|]+) \| [^|]+\|$",
                      lambda m: f"| {m.group(1).strip()} | {m.group(1).strip()} |"
                      if m.group(1).strip() not in ("English", "---") else m.group(0),
                      match.group(1))
        content = content[:match.start(1)] + body + content[match.end(1):]
    # Keyword co-occurrence cannot establish the source's financial row label.
    content = re.sub(r"(?ms)(^## HALLUCINATION_CELL_KEYWORDS\n).*?(?=^## |\Z)",
                     r"\1\n```python\n[]\n```\n\n", content)
    # Replace optional model unit conversion with a source-preserving rule.
    content = re.sub(
        r"(?ms)^4\. NUMBERS.*?(?=^5\. )",
        "4. NUMBERS: Copy numerical tokens, signs, currencies and magnitude units exactly.\n"
        "   Keep B/M/K/T and bps unchanged. Do not convert to 亿/億 or change separators.\n"
        "   Preserve source uncertainty, disclosures and all sections.\n\n", content)
    content = content.replace("First use in a paragraph", "First use in the document")
    content = content.replace("Subsequent uses in the same paragraph or later", "Subsequent uses in the document")
    return content.rstrip() + "\n"


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    for filename, traditional in (("skill_simplified.md", False), ("skill_traditional.md", True)):
        path = root / filename
        path.write_text(normalize(path.read_text(encoding="utf-8"), traditional), encoding="utf-8")
        print(f"Normalized {filename}")
