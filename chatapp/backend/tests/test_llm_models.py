from app import llm_models
from app.settings import settings


def test_bedrock_api_uses_openai_compatible_chat_model(monkeypatch):
    llm_models.ChatOpenAI.reset_mock()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "bedrock")
    monkeypatch.setattr(settings, "BEDROCK_API_KEY", "test-bedrock-key")
    monkeypatch.setattr(
        settings,
        "BEDROCK_BASE_URL",
        "https://bedrock-mantle.us-east-2.api.aws/v1",
    )
    monkeypatch.setattr(settings, "BEDROCK_MODEL_NAME", "google.gemma-3-4b-it")

    model = llm_models.create_chat_openai_model()

    assert model is llm_models.ChatOpenAI.return_value
    llm_models.ChatOpenAI.assert_called_once_with(
        openai_api_key="test-bedrock-key",
        openai_api_base="https://bedrock-mantle.us-east-2.api.aws/v1",
        model_name="google.gemma-3-4b-it",
        max_tokens=settings.BEDROCK_MAX_TOKENS,
        temperature=settings.BEDROCK_TEMPERATURE,
        verbose=settings.BEDROCK_VERBOSE,
    )