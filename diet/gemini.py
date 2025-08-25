from google import genai
from pydantic import BaseModel
from google.genai import types

import json

class Answer(BaseModel):
    verdict: str
    explanation: str


def get_verdict(product, diet_description, api_key):
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Answer,
            system_instruction="Ты профессиональный диетолог, твоя задача по описанию блюда или его составу а также диете пользователя вынести вердикт можно ли есть его или нельзя. Доступные варианты ответа \"Да\", \"Нет\", \"С осторожностью\". Также ты должен предоставить краткое объяснение своего решения."
        ),
        contents=f"Блюдо: '{product}', Диета: '{diet_description}'"
    )

    # parse json
    response_data = json.loads(response.text)
    return response_data['verdict'], response_data['explanation']