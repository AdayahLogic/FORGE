from core.models.openai_client import OpenAIClient


class ModelGateway:
    """
    Central model access point for Forge/Nexus core.

    Why this exists:
    - keeps model calls centralized
    - makes provider switching easier later
    - gives us one place for logging, routing, and safeguards
    """

    def __init__(self):
        self.openai_client = OpenAIClient()

    def generate(
        self,
        prompt: str,
        provider: str = "openai",
        model: str = "gpt-5.4",
    ) -> dict:
        if provider != "openai":
            raise ValueError(f"Unsupported provider: {provider}")

        output_text = self.openai_client.generate_text(
            prompt=prompt,
            model=model,
        )

        return {
            "provider": provider,
            "model": model,
            "output_text": output_text,
        }