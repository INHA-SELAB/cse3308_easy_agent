import json
from pathlib import Path
from datetime import datetime
from ..providers.base import LLMResponse


class ExecutionLogger:
    """실행 로그를 JSONL 형식으로 기록"""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.session_start = datetime.now()
        self.log_file = self.log_dir / f"session_{self.session_start.strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.entries = []

    def log_start(self, agent_name: str, pattern: str):
        """에이전트 실행 시작 기록"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "start",
            "agent": agent_name,
            "pattern": pattern,
        }
        self._write(entry)

    def log_complete(self, agent_name: str, response: LLMResponse):
        """에이전트 실행 완료 기록"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "complete",
            "agent": agent_name,
            "provider": response.provider,
            "elapsed_seconds": response.elapsed_seconds,
            "cost_usd": response.cost_usd,
            "response_length": len(response.text),
        }
        self._write(entry)
        self.entries.append(entry)

    def log_error(self, agent_name: str, error: Exception):
        """에이전트 실행 실패 기록"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "error",
            "agent": agent_name,
            "error": str(error),
        }
        self._write(entry)

    def _write(self, entry: dict):
        """JSONL 형식으로 한 줄 기록"""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def print_summary(self):
        """실행 요약 출력"""
        if not self.entries:
            return

        total_time = sum(e.get("elapsed_seconds", 0) for e in self.entries)
        total_cost = sum(e.get("cost_usd", 0) or 0 for e in self.entries)

        print(f"\n{'='*50}")
        print(f"실행 요약")
        print(f"{'='*50}")
        print(f"  에이전트 수: {len(self.entries)}")
        print(f"  총 소요 시간: {total_time:.1f}s")
        if total_cost > 0:
            print(f"  총 비용: ${total_cost:.4f}")
        print(f"  로그 파일: {self.log_file}")
        print(f"{'='*50}\n")
