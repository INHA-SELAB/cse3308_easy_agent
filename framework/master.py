import json
from typing import List, Tuple, Optional
from .providers.base import BaseProvider, LLMResponse
from .utils.file_context import FileContext
from .exceptions import TaskIRParseError

# ─── 단일 Phase 분해용 (decompose + execute_ir 경로, 하위 호환성) ───
MASTER_SYSTEM_PROMPT = """\
당신은 작업 분해 전문가입니다.
사용자의 요청을 분석하고, 사용 가능한 에이전트들에게 작업을 분배하는 Task IR(JSON)을 생성합니다.

사용 가능한 에이전트 목록은 [에이전트 목록] 섹션에 제공됩니다.

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트를 포함하지 마세요.

{
  "execution": "sequential" | "parallel",
  "tasks": [
    {
      "agent": "에이전트_이름",
      "prompt": "해당 에이전트에게 전달할 구체적 지시",
    }
  ]
}

규칙:
- 작업 간 의존성이 있으면 execution: "sequential"
- 작업이 독립적이면 execution: "parallel"
"""

# ─── 반복(iterative) 실행용: 각 에이전트 단계마다 Master가 호출됨 ───
MASTER_STEP_PROMPT = """\
당신은 멀티 에이전트 파이프라인의 오케스트레이터입니다.
사용자의 원래 요청을 기반으로, 아래 에이전트가 수행할 구체적인 작업 지시를 생성합니다.

[대상 에이전트]
- 이름: {agent_name}
- 역할: {agent_role}

{completed_section}

규칙:
- 에이전트에게 전달할 작업 지시만 출력하세요. 다른 텍스트를 포함하지 마세요.
- 이전 에이전트의 전체 출력은 별도로 전달되므로, 작업 지시에 출력 내용을 복사하지 마세요.
- 해당 에이전트의 역할에 맞는 작업만 지시하세요 (예: test_writer에게 코드 구현을 지시하지 마세요).
- 이전 에이전트가 생성한 파일명이나 모듈 구조를 참조하여 구체적으로 작성하세요.
- 에이전트가 추가 질문 없이 바로 작업을 시작할 수 있도록 명확하게 작성하세요.
"""


class MasterAgent:
    """
    하이브리드 Master Agent.

    두 가지 실행 모드 지원:

    1. Batch 모드 (decompose + execute_ir):
       - decompose()로 Task IR 일괄 생성 → Engine.execute_ir()로 실행
       - 하위 호환성 유지

    2. Iterative 모드 (generate_step_task 반복):
       - Engine.run_master()에서 사용
       - 각 에이전트 실행 전 Master가 개입하여 작업 지시 생성
       - Master → agent → Master → agent → ... 패턴
    """

    def __init__(self, provider: BaseProvider, context: FileContext):
        self.provider = provider
        self.context = context

    # ═══════════════════════════════════════════════════════
    # Iterative 모드: 단계별 작업 지시 생성
    # ═══════════════════════════════════════════════════════

    async def generate_step_task(
        self,
        user_request: str,
        target_agent,
        completed_tasks: List[Tuple[str, LLMResponse]],
        requirements_file: Optional[str] = None,
    ) -> str:
        """
        반복 실행 모드: 특정 에이전트를 위한 작업 지시를 생성.

        Master LLM이 사용자 요청 + 이전 완료 내역을 보고,
        target_agent에게 전달할 구체적 prompt를 생성한다.

        Args:
            user_request: 사용자의 원래 요청
            target_agent: 작업을 받을 Agent 객체
            completed_tasks: [(agent_name, LLMResponse), ...] 완료된 작업 목록
            requirements_file: 요구사항 명세서 경로 (있으면 컨텍스트에 포함)

        Returns:
            str: target_agent에게 전달할 작업 지시 텍스트
        """
        # 완료된 작업 요약 구성
        if completed_tasks:
            lines = []
            for name, resp in completed_tasks:
                max_summary = max(300, min(2000, self.provider.max_context_chars // 50))
                summary = resp.text[:max_summary].replace("\n", " ")
                if len(resp.text) > max_summary:
                    summary += "..."
                lines.append(f"- {name}: {summary}")
            completed_section = "[이전 완료된 작업]\n" + "\n".join(lines)
        else:
            completed_section = "[이전 완료된 작업]\n없음 (첫 번째 에이전트)"

        system_prompt = MASTER_STEP_PROMPT.format(
            agent_name=target_agent.name,
            agent_role=target_agent.role,
            completed_section=completed_section,
        )

        response = await self.provider.call(
            system_prompt=system_prompt,
            user_message=user_request,
            requirements_file=requirements_file,
            cwd=str(self.context.session_dir),
        )

        return response.text

    # ═══════════════════════════════════════════════════════
    # Batch 모드: Task IR 일괄 생성 (하위 호환성)
    # ═══════════════════════════════════════════════════════

    async def decompose(self, user_request: str, available_agents: list) -> dict:
        """
        사용자 요청을 Task IR로 분해 (Batch 모드).

        run_master()에서는 사용하지 않음.
        수동으로 decompose() + execute_ir()를 호출할 때 사용.
        """
        agent_descriptions = "\n".join(
            f"- {a.name}: {a.role}" for a in available_agents
        )

        full_prompt = (
            f"[사용자 요청]\n{user_request}\n\n"
            f"[에이전트 목록]\n{agent_descriptions}"
        )

        response = await self.provider.call(
            system_prompt=MASTER_SYSTEM_PROMPT,
            user_message=full_prompt,
            cwd=str(self.context.session_dir),
        )

        task_ir = self._parse_task_ir(response.text)
        self.context.save_task_ir(task_ir)
        return task_ir

    def _parse_task_ir(self, text: str) -> dict:
        """LLM 응답에서 JSON을 추출하여 Task IR로 파싱 (M-003: TaskIRParseError)"""
        cleaned = text.strip()

        # Strategy 1: code fence extraction
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        # Strategy 2: if still not valid JSON, find first { to last }
        try:
            ir = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    ir = json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    raise TaskIRParseError(text)
            else:
                raise TaskIRParseError(text)

        if "execution" not in ir or "tasks" not in ir:
            raise TaskIRParseError(text)

        if ir["execution"] not in ("sequential", "parallel"):
            raise TaskIRParseError(text)

        return ir
