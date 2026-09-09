from huggingface_hub import InferenceClient

from package.config import HF_TOKEN


MODEL_NAME = "Qwen/Qwen3-8B"


def get_llm_client() -> InferenceClient:
    """
    Create the shared Hugging Face inference client.

    Qwen3 thinking mode is disabled because the agents require concise,
    structured outputs rather than separate reasoning content.
    """

    if not HF_TOKEN:
        raise RuntimeError(
            "HF_TOKEN is not configured. Add it to the project .env file."
        )

    return InferenceClient(
        model=MODEL_NAME,
        token=HF_TOKEN,
    )


def chat_completion(messages, **kwargs):
    """
    Send a chat-completion request with Qwen3 thinking disabled.
    """

    client = get_llm_client()

    return client.chat_completion(
        messages=messages,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
        **kwargs,
    )