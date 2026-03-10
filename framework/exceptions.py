"""Agent Lab 커스텀 예외 계층 (M-003)"""


class AgentLabError(Exception):
    """Agent Lab 기본 예외"""
    pass


class ProviderNotFoundError(AgentLabError):
    """CLI 도구가 설치되지 않았을 때"""
    def __init__(self, provider: str):
        super().__init__(
            f"'{provider}' CLI를 찾을 수 없습니다.\n"
            f"설치 확인: https://docs.example.com/setup#{provider}"
        )


class ProviderTimeoutError(AgentLabError):
    """CLI 호출 타임아웃"""
    def __init__(self, provider: str, timeout: int):
        super().__init__(
            f"'{provider}' 응답 대기 시간 초과 ({timeout}초).\n"
            f"네트워크 연결을 확인하거나, config.json에서 timeout 값을 늘려보세요."
        )


class ProviderCallError(AgentLabError):
    """CLI 호출 실패"""
    def __init__(self, provider: str, detail: str):
        super().__init__(
            f"'{provider}' CLI 호출 실패:\n{detail}"
        )


class TaskIRParseError(AgentLabError):
    """Master Agent의 Task IR 파싱 실패"""
    def __init__(self, raw_text: str):
        super().__init__(
            f"Master Agent가 유효한 Task IR을 생성하지 못했습니다.\n"
            f"다시 시도하거나, 요청을 더 구체적으로 작성해보세요.\n"
            f"원본 응답 (디버깅용):\n{raw_text[:500]}"
        )
