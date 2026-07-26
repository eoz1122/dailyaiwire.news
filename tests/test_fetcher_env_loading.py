import importlib
import os
import sys
from contextlib import contextmanager

import dotenv


_MISSING = object()


@contextmanager
def _preserve_import_state(*module_names: str):
    names = set(module_names)
    for module_name in module_names:
        if "." in module_name:
            names.add(module_name.rsplit(".", 1)[0])

    module_snapshot = {
        module_name: sys.modules.get(module_name, _MISSING)
        for module_name in names
    }
    parent_attributes = {}
    for module_name in module_names:
        if "." not in module_name:
            continue
        parent_name, attribute_name = module_name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            parent_attributes[(parent, attribute_name)] = getattr(
                parent,
                attribute_name,
                _MISSING,
            )

    try:
        yield
    finally:
        for module_name, original_module in module_snapshot.items():
            if original_module is _MISSING:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = original_module

        for (parent, attribute_name), original_value in parent_attributes.items():
            if original_value is _MISSING:
                try:
                    delattr(parent, attribute_name)
                except AttributeError:
                    pass
            else:
                setattr(parent, attribute_name, original_value)


def _fresh_import(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _assert_module_loads_dotenv_before_ai_config(monkeypatch, module_name: str):
    with monkeypatch.context() as isolated:
        isolated.delenv("GEMINI_ARTICLE_MODEL", raising=False)

        def fake_load_dotenv(*args, **kwargs):
            isolated.setenv(
                "GEMINI_ARTICLE_MODEL",
                "gemini-2.5-flash-lite",
            )
            return True

        isolated.setattr(dotenv, "load_dotenv", fake_load_dotenv)
        with _preserve_import_state(module_name, "ai_config"):
            sys.modules.pop(module_name, None)
            sys.modules.pop("ai_config", None)

            module = _fresh_import(module_name)

            assert module.ai_config.DEFAULT_MODEL == "gemini-2.5-flash-lite"


def _assert_fetcher_package_loads_runtime_knobs(monkeypatch):
    with monkeypatch.context() as isolated:
        isolated.delenv("FETCHER_BATCH_SIZE", raising=False)

        def fake_load_dotenv(*args, **kwargs):
            isolated.setenv("FETCHER_BATCH_SIZE", "3")
            return True

        isolated.setattr(dotenv, "load_dotenv", fake_load_dotenv)
        with _preserve_import_state("fetcher"):
            sys.modules.pop("fetcher", None)

            module = _fresh_import("fetcher")

            assert module.os.getenv("FETCHER_BATCH_SIZE") == "3"


def test_ai_processor_loads_dotenv_before_ai_config(monkeypatch):
    _assert_module_loads_dotenv_before_ai_config(monkeypatch, "fetcher.ai_processor")


def test_sources_loads_dotenv_before_ai_config(monkeypatch):
    _assert_module_loads_dotenv_before_ai_config(monkeypatch, "fetcher.sources")


def test_fetcher_package_loads_dotenv_before_reading_runtime_knobs(monkeypatch):
    _assert_fetcher_package_loads_runtime_knobs(monkeypatch)


def test_ai_config_import_check_restores_process_state(monkeypatch):
    missing = object()
    original_env = os.environ.get("GEMINI_ARTICLE_MODEL", missing)
    original_module = sys.modules.get("fetcher.ai_processor", missing)
    original_ai_config = sys.modules.get("ai_config", missing)

    _assert_module_loads_dotenv_before_ai_config(
        monkeypatch,
        "fetcher.ai_processor",
    )

    current_env = os.environ.get("GEMINI_ARTICLE_MODEL", missing)
    if original_env is missing:
        assert current_env is missing
    else:
        assert current_env == original_env
    assert sys.modules.get("fetcher.ai_processor", missing) is original_module
    assert sys.modules.get("ai_config", missing) is original_ai_config


def test_fetcher_package_import_check_restores_process_state(monkeypatch):
    missing = object()
    original_env = os.environ.get("FETCHER_BATCH_SIZE", missing)
    original_module = sys.modules.get("fetcher", missing)

    _assert_fetcher_package_loads_runtime_knobs(monkeypatch)

    current_env = os.environ.get("FETCHER_BATCH_SIZE", missing)
    if original_env is missing:
        assert current_env is missing
    else:
        assert current_env == original_env
    assert sys.modules.get("fetcher", missing) is original_module
