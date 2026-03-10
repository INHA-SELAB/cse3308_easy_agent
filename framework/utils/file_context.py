import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional


class FileContext:
    """
    에이전트 간 파일 기반 컨텍스트 관리.

    각 세션은 workspace/{session_id}/ 하위에 파일을 생성하며,
    에이전트의 출력은 파일로 저장되고, 다음 에이전트에게 경로로 전달된다.
    """

    def __init__(self, workspace_dir: str = "workspace"):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.session_dir = Path(workspace_dir) / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.requirements_path: Optional[str] = None

    def save_output(self, agent_name: str, content: str) -> str:
        """에이전트 출력을 파일로 저장하고 경로를 반환"""
        filename = f"agent_{agent_name}_output.md"
        filepath = self.session_dir / filename
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)

    def save_task_ir(self, task_ir: dict) -> str:
        """Master Agent의 Task IR을 파일로 저장"""
        filepath = self.session_dir / "task_ir.json"
        filepath.write_text(json.dumps(task_ir, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(filepath)

    def get_previous_output(self, agent_name: str) -> str:
        """이전 에이전트의 출력 파일 경로를 반환"""
        filepath = self.session_dir / f"agent_{agent_name}_output.md"
        if not filepath.exists():
            raise FileNotFoundError(f"이전 에이전트 출력 없음: {filepath}")
        return str(filepath)

    def save_requirements(self, content: str) -> str:
        """요구사항 명세서를 파일로 저장하고 경로를 반환"""
        filepath = self.session_dir / "requirements.md"
        filepath.write_text(content, encoding="utf-8")
        self.requirements_path = str(filepath)
        return self.requirements_path

    def save_agent_requirements(self, agent_name: str, content: str) -> str:
        """에이전트별 개별 요구사항을 파일로 저장하고 경로를 반환"""
        filepath = self.session_dir / f"requirements_{agent_name}.md"
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)

    def save_final_result(self, content: str) -> str:
        """최종 합성 결과를 저장"""
        filepath = self.session_dir / "final_result.md"
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)
