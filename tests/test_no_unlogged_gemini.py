from pathlib import Path


def test_no_direct_generativeai_calls_outside_gateway():
    root = Path(__file__).resolve().parents[1]
    scan_roots = [
        root / "fetcher",
        root / "scripts",
        root / "services",
    ]
    allowed = {root / "services" / "ai_gateway.py"}
    offenders = []

    for scan_root in scan_roots:
        for path in scan_root.rglob("*.py"):
            if path in allowed:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "google.generativeai" in text or "genai.GenerativeModel" in text:
                offenders.append(str(path.relative_to(root)))

    assert offenders == []
