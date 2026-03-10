"""
파이프라인 실행 추적(Trace) 수집기.

에이전트가 어떤 순서로, 무슨 프롬프트를 받고, 얼마나 걸렸는지를
구조화된 이벤트로 기록한다. 학생은 trace.jsonl 파일이나
print_trace()로 파이프라인의 전체 흐름을 확인할 수 있다.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class TraceEvent:
    """파이프라인에서 발생한 단일 이벤트"""
    timestamp: str
    event: str          # pipeline_start, master_think, agent_start, agent_complete, agent_error, pipeline_end
    agent: Optional[str] = None
    pattern: Optional[str] = None       # single, sequential, parallel, master
    prompt_preview: Optional[str] = None
    output_preview: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None
    detail: Optional[str] = None


# 이벤트 타입별 터미널 표시 기호
_SYMBOLS = {
    "pipeline_start": ">>",
    "pipeline_end":   "<<",
    "master_think":   "??",
    "agent_start":    "->",
    "agent_complete": "OK",
    "agent_error":    "!!",
}


class TraceCollector:
    """세션 단위로 TraceEvent를 수집하고 저장"""

    def __init__(self):
        self.events: List[TraceEvent] = []
        self._file: Optional[Path] = None

    def bind(self, session_dir: Path):
        """세션 디렉토리에 trace.jsonl 파일 바인딩"""
        self._file = session_dir / "trace.jsonl"

    def _preview(self, text: Optional[str], limit: int = 200) -> Optional[str]:
        if not text:
            return None
        one_line = text.replace("\n", " ").strip()
        if len(one_line) > limit:
            return one_line[:limit] + "..."
        return one_line

    def emit(self, event: str, **kwargs):
        """이벤트 기록"""
        # prompt/output은 미리보기로 축약
        if "prompt_preview" in kwargs and kwargs["prompt_preview"]:
            kwargs["prompt_preview"] = self._preview(kwargs["prompt_preview"])
        if "output_preview" in kwargs and kwargs["output_preview"]:
            kwargs["output_preview"] = self._preview(kwargs["output_preview"])

        entry = TraceEvent(
            timestamp=datetime.now().isoformat(),
            event=event,
            **kwargs,
        )
        self.events.append(entry)

        # 파일에 즉시 기록
        if self._file:
            with open(self._file, "a", encoding="utf-8") as f:
                row = {k: v for k, v in asdict(entry).items() if v is not None}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def print_trace(self):
        """학생용: 파이프라인 실행 흐름을 한눈에 출력"""
        if not self.events:
            print("  (트레이스 없음)")
            return

        print()
        print("=" * 60)
        print("  Pipeline Trace")
        print("=" * 60)

        for e in self.events:
            sym = _SYMBOLS.get(e.event, "  ")
            ts = e.timestamp[11:19]  # HH:MM:SS

            if e.event == "pipeline_start":
                print(f"  [{sym}] {ts}  {e.pattern} 파이프라인 시작")
            elif e.event == "pipeline_end":
                print(f"  [{sym}] {ts}  파이프라인 종료 ({e.elapsed_seconds:.1f}s)")
            elif e.event == "master_think":
                print(f"  [{sym}] {ts}  Master -> {e.agent} 지시 생성 ({e.elapsed_seconds:.1f}s)")
                if e.prompt_preview:
                    print(f"           프롬프트: {e.prompt_preview[:80]}")
            elif e.event == "agent_start":
                print(f"  [{sym}] {ts}  {e.agent} 실행 시작")
            elif e.event == "agent_complete":
                print(f"  [{sym}] {ts}  {e.agent} 완료 ({e.elapsed_seconds:.1f}s)")
                if e.output_preview:
                    print(f"           출력: {e.output_preview[:80]}")
            elif e.event == "agent_error":
                print(f"  [{sym}] {ts}  {e.agent} 실패: {e.error}")
            else:
                print(f"  [  ] {ts}  {e.event} {e.detail or ''}")

        print("=" * 60)

        # 요약 통계
        agents = [e for e in self.events if e.event == "agent_complete"]
        errors = [e for e in self.events if e.event == "agent_error"]
        total = sum(e.elapsed_seconds or 0 for e in agents)
        print(f"  에이전트: {len(agents)}개 완료, {len(errors)}개 실패")
        print(f"  총 에이전트 시간: {total:.1f}s")
        if self._file:
            print(f"  트레이스 파일: {self._file}")
        print("=" * 60)
        print()
