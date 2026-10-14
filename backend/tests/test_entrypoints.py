from importlib import import_module


def test_api_and_worker_have_explicit_entrypoints():
    assert callable(import_module("app.main").create_application)
    assert callable(import_module("app.worker").main)
