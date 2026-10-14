import sys
import types
from unittest.mock import Mock

import pytest

from execution.gemini_client import generate_gemini_text


def _install_fake_sdk(monkeypatch, client):
    fake_google = types.ModuleType("google")
    fake_google.__path__ = []
    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = Mock(return_value=client)
    fake_types = types.SimpleNamespace(
        HttpOptions=Mock(side_effect=lambda **kwargs: kwargs),
        HttpRetryOptions=Mock(side_effect=lambda **kwargs: kwargs),
    )
    fake_google.genai = fake_genai
    fake_genai.types = fake_types
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    return fake_genai, fake_types


def test_generate_gemini_text_trims_key_and_bounds_retries(monkeypatch):
    response = types.SimpleNamespace(text="  Market read  ")
    client = Mock()
    client.models.generate_content.return_value = response
    fake_genai, fake_types = _install_fake_sdk(monkeypatch, client)

    result = generate_gemini_text("prompt", model_name="flash", api_key="  key\n")

    assert result == "Market read"
    fake_genai.Client.assert_called_once_with(
        api_key="key",
        http_options={"timeout": 60_000, "retry_options": {"attempts": 1}},
    )
    fake_types.HttpRetryOptions.assert_called_once_with(attempts=1)
    client.models.generate_content.assert_called_once_with(model="flash", contents="prompt")
    client.close.assert_called_once()


def test_generate_gemini_text_rejects_missing_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="not configured"):
        generate_gemini_text("prompt", api_key="  ")
