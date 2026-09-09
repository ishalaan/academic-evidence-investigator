import pytest

from package.services import llm


def test_missing_hf_token_raises_error(monkeypatch):
    monkeypatch.setattr(llm, "HF_TOKEN", None)

    with pytest.raises(
        RuntimeError,
        match="HF_TOKEN is not configured",
    ):
        llm.get_llm_client()


def test_llm_client_is_created_when_token_exists(monkeypatch):
    monkeypatch.setattr(llm, "HF_TOKEN", "fake-token")

    class FakeInferenceClient:
        def __init__(self, model, token):
            self.model = model
            self.token = token

    monkeypatch.setattr(
        llm,
        "InferenceClient",
        FakeInferenceClient,
    )

    client = llm.get_llm_client()

    assert client.model == llm.MODEL_NAME
    assert client.token == "fake-token"