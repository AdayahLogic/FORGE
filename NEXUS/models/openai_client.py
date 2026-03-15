import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class OpenAIClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment.")

        self.client = OpenAI(api_key=api_key)

    def generate_text(
        self,
        prompt: str,
        model: str = "gpt-5.4",
    ) -> str:
        response = self.client.responses.create(
            model=model,
            input=prompt
        )
        return response.output_text.strip()