"""Claude API 호출 래퍼: 채팅 스트리밍과 보고서용 구조화 출력."""

from collections.abc import Iterator

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
# 안전 분류기가 요청을 거절하면 서버가 다른 모델로 자동 재시도하도록 켠다.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """화면에 그대로 보여줄 수 있는 한국어 오류."""


def make_client(api_key: str | None = None) -> anthropic.Anthropic:
    # api_key가 없으면 SDK가 ANTHROPIC_API_KEY 환경변수 등에서 찾는다.
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def _friendly(err: Exception) -> LLMError:
    if isinstance(err, anthropic.AuthenticationError):
        return LLMError("API 키가 올바르지 않습니다. 왼쪽에서 키를 다시 확인해 주세요.")
    if isinstance(err, anthropic.RateLimitError):
        return LLMError("요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    if isinstance(err, anthropic.APIConnectionError):
        return LLMError("Claude API에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.")
    if isinstance(err, anthropic.APIStatusError):
        return LLMError(f"API 오류({err.status_code}): {err.message}")
    return LLMError(str(err))


class ChatStream:
    """반복하면 답변 텍스트 조각이 나오고, 다 돌고 나면 .final 에 전체 응답 메시지가 담긴다.

    다음 턴에는 .final.content 를 그대로 대화 기록에 넣어야 한다(thinking 블록 보존).
    """

    def __init__(self, client: anthropic.Anthropic, system: list[dict], messages: list[dict], effort: str = "medium"):
        self._args = dict(
            model=MODEL,
            max_tokens=16000,
            system=system,
            messages=messages,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        self._client = client
        self.final = None

    def __iter__(self) -> Iterator[str]:
        try:
            with self._client.beta.messages.stream(**self._args) as stream:
                yield from stream.text_stream
                self.final = stream.get_final_message()
        except anthropic.APIError as err:
            raise _friendly(err) from err
        if self.final.stop_reason == "refusal":
            raise LLMError("이 요청은 처리할 수 없습니다. 질문을 바꿔서 다시 시도해 주세요.")


def parse_structured(
    client: anthropic.Anthropic,
    system: str,
    prompt: str,
    schema: type[BaseModel],
) -> BaseModel:
    """보고서 생성용: 스키마에 맞는 JSON을 받아 검증된 객체로 돌려준다."""
    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": "high"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.APIError as err:
        raise _friendly(err) from err
    if response.stop_reason == "refusal":
        raise LLMError("보고서를 만들 수 없는 내용입니다.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise LLMError("보고서가 너무 길어 끝까지 만들지 못했습니다. 대화를 줄여서 다시 시도해 주세요.")
    return response.parsed_output
