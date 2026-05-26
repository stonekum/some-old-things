from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from striprtf.striprtf import rtf_to_text


def _scrub(text: str) -> str:
    # RTF→text can leave lone surrogates that break UTF-8 encoding; drop them.
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


def _read_history_file(p: Path) -> str:
    raw = p.read_bytes()
    text = ""
    if p.suffix.lower() == ".rtf":
        try:
            text = rtf_to_text(raw.decode("utf-8", errors="ignore"))
        except Exception as e:
            logger.warning(f"rtf parse failed for {p}: {e}")
            text = raw.decode("utf-8", errors="ignore")
    else:
        text = raw.decode("utf-8", errors="ignore")
    return _scrub(text).strip()


def build_style_seed(history_dir: Path, out_path: Path) -> dict:
    """Distill history examples to a compact style summary, persisted to disk."""
    samples: list[str] = []
    if history_dir.exists():
        for p in sorted(history_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in {".rtf", ".txt", ".md"}:
                text = _read_history_file(p)
                if text:
                    samples.append(text)

    summary = {
        "sample_count": len(samples),
        "openers": [_first_line(s) for s in samples[:5]],
        "avg_paragraphs": sum(_paragraph_count(s) for s in samples) // max(len(samples), 1),
        "raw_excerpts": [s[:240] for s in samples[:3]],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:80]
    return ""


def _paragraph_count(text: str) -> int:
    return max(1, len([p for p in text.split("\n\n") if p.strip()]))


def load_style_seed(path: Path) -> str:
    """Return a short string suitable for embedding into a generation prompt."""
    if not path.exists():
        return "(no historical style seed available)"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "(corrupt style seed)"
    lines = []
    if data.get("openers"):
        lines.append("Opening patterns observed in past posts:")
        for o in data["openers"]:
            lines.append(f"  - {o}")
    if data.get("avg_paragraphs"):
        lines.append(f"Typical paragraph count: ~{data['avg_paragraphs']}.")
    if data.get("raw_excerpts"):
        lines.append("Excerpt fragments (tone reference only, do not copy):")
        for ex in data["raw_excerpts"]:
            lines.append(f"  > {ex}")
    return "\n".join(lines) or "(empty style seed)"
