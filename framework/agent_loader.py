import json
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Agent:
    """JSON에서 로드된 에이전트 객체"""
    name: str
    role: str
    system_prompt: str
    output_format: str  # markdown | json | text

    def __repr__(self):
        return f"Agent(name='{self.name}', role='{self.role}')"


def load_agent(name: str, agents_dir: str = "agents") -> Agent:
    """agents/ 디렉토리에서 JSON 파일을 읽어 Agent 객체로 변환"""
    path = Path(agents_dir) / f"{name}.json"

    if not path.exists():
        raise FileNotFoundError(f"에이전트 정의 파일 없음: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    required_fields = ["name", "role", "system_prompt"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"에이전트 '{name}'에 필수 필드 누락: {field}")

    return Agent(
        name=data["name"],
        role=data["role"],
        system_prompt=data["system_prompt"],
        output_format=data.get("output_format", "markdown"),
    )
