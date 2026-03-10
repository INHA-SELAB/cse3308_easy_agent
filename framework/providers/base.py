from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LLMResponse:
    """모든 프로바이더의 공통 응답 형식"""
    text: str
    provider: str
    elapsed_seconds: float
    cost_usd: Optional[float]
    raw: dict


DEFAULT_MAX_CONTEXT_CHARS = 50000


class BaseProvider(ABC):
    """프로바이더 어댑터 추상 클래스"""

    DEFAULT_TIMEOUT = 600

    def __init__(
        self,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
        provider_config: Optional[dict] = None,
    ):
        self.max_context_chars = max_context_chars
        self.provider_config = provider_config or {}

    @abstractmethod
    async def call(
        self,
        system_prompt: str,
        user_message: str,
        input_file: Optional[str] = None,
        requirements_file: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        cwd: Optional[str] = None,
    ) -> LLMResponse:
        pass

    def _build_message(
        self,
        system_prompt: str,
        user_message: str,
        input_file: Optional[str] = None,
        requirements_file: Optional[str] = None,
    ) -> str:
        """시스템 프롬프트 + 요구사항 + 사용자 메시지 + 파일 내용을 단일 프롬프트로 조합"""
        parts = [f"[시스템 지시]\n{system_prompt}"]
        if requirements_file:
            content = Path(requirements_file).read_text(encoding="utf-8")
            if len(content) > self.max_context_chars // 2:
                content = content[:self.max_context_chars // 2] + "\n\n... (truncated)"
            parts.append(f"\n[요구사항 명세서]\n{content}")
        parts.append(f"\n[작업 요청]\n{user_message}")
        if input_file:
            content = Path(input_file).read_text(encoding="utf-8")
            remaining = self.max_context_chars - sum(len(p) for p in parts)
            if remaining <= 0:
                pass  # 컨텍스트 예산 소진 — 이전 출력 생략
            else:
                if len(content) > remaining:
                    content = content[:remaining] + "\n\n... (truncated)"
                parts.append(f"\n[이전 에이전트 출력]\n{content}")
        return "\n".join(parts)
