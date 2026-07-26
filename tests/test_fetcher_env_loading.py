import importlib
import os
import sys

import dotenv


def _fresh_import(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _assert_module_loads_dotenv_before_ai_config(monkeypatch, module_name: str):
    monkeypatch.delenv("GEMINI_ARTICLE_MODEL", raising=False)

    original_load_dotenv = dotenv.load_dotenv

    def fake_load_dotenv(*args, **kwargs):
        os.environ["GEMINI_ARTICLE_MODEL"] = "gemini-2.5-flash-lite"
        return original_load_dotenv(*args, **kwargs)

    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)
    sys.modules.pop(module_name, None)
    sys.modules.pop("ai_config", None)

    module = _fresh_import(module_name)

    assert module.ai_config.DEFAULT_MODEL == "gemini-2.5-flash-lite"


def test_ai_processor_loads_dotenv_before_ai_config(monkeypatch):
    _assert_module_loads_dotenv_before_ai_config(monkeypatch, "fetcher.ai_processor")


def test_sources_loads_dotenv_before_ai_config(monkeypatch):
    _assert_module_loads_dotenv_before_ai_config(monkeypatch, "fetcher.sources")


def test_fetcher_package_loads_dotenv_before_reading_runtime_knobs(monkeypatch):
    monkeypatch.delenv("FETCHER_BATCH_SIZE", raising=False)

    original_load_dotenv = dotenv.load_dotenv

    def fake_load_dotenv(*args, **kwargs):
        os.environ["FETCHER_BATCH_SIZE"] = "3"
        return original_load_dotenv(*args, **kwargs)

    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)
    sys.modules.pop("fetcher", None)

    module = _fresh_import("fetcher")

    assert module.os.getenv("FETCHER_BATCH_SIZE") == "3"
