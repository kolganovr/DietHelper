import enum
import json
import logging

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

MODEL = "gemini-3.1-flash-lite"

SYSTEM_INSTRUCTION = (
    "Ты профессиональный диетолог. По названию или составу блюда и диете пользователя "
    "вынеси вердикт, можно ли его есть. Варианты вердикта: \"Можно\", \"Нельзя\", "
    "\"С осторожностью\". В explanation дай краткое объяснение (2-3 предложения). "
    "В reasons перечисли конкретные ингредиенты или свойства блюда, которые повлияли на вердикт "
    "(до 4 коротких пунктов). В alternatives предложи, чем заменить блюдо или как его "
    "приготовить, чтобы оно подходило под диету (до 3 пунктов; пусто, если вердикт \"Можно\")."
)


class Verdict(str, enum.Enum):
    OK = "Можно"
    NO = "Нельзя"
    CAUTION = "С осторожностью"


class Answer(BaseModel):
    verdict: Verdict
    explanation: str
    reasons: list[str] = []
    alternatives: list[str] = []


class GeminiError(Exception):
    """Ошибка запроса к Gemini с понятным пользователю текстом.
    kind: key (ключ недействителен), quota (лимит), unavailable (временный сбой)."""

    def __init__(self, kind, title, message):
        super().__init__(message)
        self.kind = kind
        self.title = title
        self.message = message


def normalize_verdict(raw):
    """Привести вердикт к одному из трёх значений, None если не распознан."""
    text = str(getattr(raw, "value", raw)).strip().strip(".!").lower()
    for verdict in Verdict:
        if text == verdict.value.lower():
            return verdict.value
    return None


def _classify(e):
    message = str(e).lower()
    code = getattr(e, "code", None)
    if code in (401, 403) or (code == 400 and "api key" in message) or "api_key_invalid" in message:
        return GeminiError(
            "key", "Ключ Gemini не подходит",
            "Google отклонил API-ключ. Проверьте, что он скопирован целиком, или создайте новый в настройках.",
        )
    if code == 429:
        return GeminiError(
            "quota", "Лимит запросов исчерпан",
            "Бесплатная квота Gemini на сегодня или на эту минуту закончилась. Подождите немного и повторите.",
        )
    return GeminiError(
        "unavailable", "Gemini не ответил",
        "Сервис временно недоступен. Попробуйте ещё раз через минуту.",
    )


def get_verdict(product, diet_description, api_key):
    """Вернуть dict: verdict, explanation, reasons, alternatives. При сбое бросает GeminiError."""
    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model=MODEL,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Answer,
                system_instruction=SYSTEM_INSTRUCTION,
            ),
            contents=f"Блюдо: '{product}'\nДиета: '{diet_description}'",
        )
    except errors.APIError as e:
        logger.warning("Gemini API error %s: %s", getattr(e, "code", "?"), e)
        raise _classify(e) from e
    except Exception as e:
        logger.warning("Gemini request failed: %s", e)
        raise _classify(e) from e

    try:
        data = json.loads(response.text)
    except (TypeError, ValueError) as e:
        logger.warning("Gemini returned non-JSON: %r", response.text)
        raise GeminiError("unavailable", "Не удалось разобрать ответ",
                          "Модель ответила в неожиданном формате. Попробуйте ещё раз.") from e

    verdict = normalize_verdict(data.get("verdict"))
    if verdict is None:
        logger.warning("Unknown verdict: %r", data.get("verdict"))
        raise GeminiError("unavailable", "Не удалось разобрать ответ",
                          "Модель не дала однозначного вердикта. Попробуйте переформулировать запрос.")

    return {
        "verdict": verdict,
        "explanation": str(data.get("explanation", "")).strip(),
        "reasons": [str(r).strip() for r in data.get("reasons") or [] if str(r).strip()][:4],
        "alternatives": [str(a).strip() for a in data.get("alternatives") or [] if str(a).strip()][:3],
    }
