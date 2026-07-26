import ast
import codecs
import subprocess
from pathlib import Path


GEMINI_MODULES = {"google.genai", "google.generativeai"}
GEMINI_NAMES = {"genai", "generativeai"}


def _imports_gemini_sdk(path: Path) -> bool:
    raw_source = path.read_bytes()
    if raw_source.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        source = raw_source.decode("utf-16")
    else:
        source = raw_source.decode("utf-8-sig")

    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name in GEMINI_MODULES for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module in GEMINI_MODULES:
                return True
            if node.module == "google" and any(
                alias.name in GEMINI_NAMES for alias in node.names
            ):
                return True
    return False


def _find_direct_gemini_clients(paths, *, allowed):
    allowed = {path.resolve() for path in allowed}
    return [
        path
        for path in paths
        if path.resolve() not in allowed and _imports_gemini_sdk(path)
    ]


def _tracked_production_python_files(root: Path):
    result = subprocess.run(
        ["git", "ls-files", "--", "*.py"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        root / relative_path
        for relative_path in result.stdout.splitlines()
        if relative_path and not relative_path.startswith("tests/")
    ]


def test_guard_detects_current_genai_client(tmp_path):
    direct_client = tmp_path / "direct_client.py"
    direct_client.write_text(
        "from google import genai\nclient = genai.Client(api_key='test')\n",
        encoding="utf-8",
    )

    assert _find_direct_gemini_clients([direct_client], allowed=set()) == [
        direct_client
    ]


def test_guard_allows_current_client_inside_gateway(tmp_path):
    gateway = tmp_path / "ai_gateway.py"
    gateway.write_text(
        "from google import genai\nclient = genai.Client(api_key='test')\n",
        encoding="utf-8",
    )

    assert _find_direct_gemini_clients([gateway], allowed={gateway}) == []


def test_no_direct_generativeai_calls_outside_gateway():
    root = Path(__file__).resolve().parents[1]
    allowed = {root / "services" / "ai_gateway.py"}
    paths = _tracked_production_python_files(root)
    offenders = [
        str(path.relative_to(root))
        for path in _find_direct_gemini_clients(paths, allowed=allowed)
    ]

    assert offenders == []
