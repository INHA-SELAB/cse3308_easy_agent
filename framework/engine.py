import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from .agent_loader import Agent, load_agent
from .master import MasterAgent
from .providers import create_provider
from .providers.base import BaseProvider, LLMResponse
from .utils.file_context import FileContext
from .utils.logger import ExecutionLogger
from .utils.trace import TraceCollector


class Engine:
    """
    에이전트 실행 엔진.

    학생은 이 클래스를 통해 에이전트를 로드하고,
    sequential() 또는 parallel()로 실행 패턴을 선택한다.
    """

    def __init__(self, config_path: str = "config.json", provider: Optional[str] = None):
        with open(config_path, encoding="utf-8") as f:
            self._config = json.load(f)
        if provider:
            self._config["provider"] = provider
        self.provider: BaseProvider = create_provider(self._config)
        self.context = FileContext(self._config.get("workspace_dir", "workspace"))
        self.logger = ExecutionLogger(self._config.get("log_dir", "logs"))
        self.master = MasterAgent(self.provider, self.context)
        self.trace = TraceCollector()
        self.trace.bind(self.context.session_dir)
        self._agents: Dict[str, Agent] = {}

    def new_session(self):
        """새 세션 시작 -FileContext + Logger 리셋 (M-001)"""
        self.context = FileContext(self._config.get("workspace_dir", "workspace"))
        self.logger = ExecutionLogger(self._config.get("log_dir", "logs"))
        self.master = MasterAgent(self.provider, self.context)
        self.trace = TraceCollector()
        self.trace.bind(self.context.session_dir)
        self._agents = {}  # 에이전트 캐시 초기화
        return self

    def load_agent(self, name: str) -> Agent:
        """agents/ 디렉토리에서 에이전트를 로드하고 캐시"""
        if name not in self._agents:
            agents_dir = self._config.get("agents_dir", "agents")
            self._agents[name] = load_agent(name, agents_dir)
        return self._agents[name]

    async def run(
        self,
        agent: Agent,
        prompt: str,
        input_file: Optional[str] = None,
        requirements_file: Optional[str] = None,
    ) -> LLMResponse:
        """단일 에이전트 실행."""
        self.logger.log_start(agent.name, "single")
        self.trace.emit("agent_start", agent=agent.name, prompt_preview=prompt)

        response = await self.provider.call(
            system_prompt=agent.system_prompt,
            user_message=prompt,
            input_file=input_file,
            requirements_file=requirements_file,
            cwd=str(self.context.session_dir),
        )

        self.context.save_output(agent.name, response.text)
        self.logger.log_complete(agent.name, response)
        self.trace.emit("agent_complete", agent=agent.name,
                        elapsed_seconds=response.elapsed_seconds,
                        output_preview=response.text)
        print(f"  [OK] [{agent.name}] 완료 ({response.elapsed_seconds:.1f}s)")

        return response

    async def sequential(
        self,
        steps: List[Tuple[Agent, Dict]],
        requirements_file: Optional[str] = None,
    ) -> List[LLMResponse]:
        """Sequential 패턴: 에이전트를 순차 실행하며, 이전 결과를 다음에 전달."""
        print(f"\n>> Sequential 실행 시작 ({len(steps)}개 에이전트)")
        print(f"  순서: {' -> '.join(a.name for a, _ in steps)}\n")
        self.trace.emit("pipeline_start", pattern="sequential",
                        detail=f"{len(steps)}개 에이전트")

        total_start = time.time()
        previous_output_path: Optional[str] = None
        responses: List[LLMResponse] = []

        for agent, params in steps:
            self.logger.log_start(agent.name, "sequential")
            self.trace.emit("agent_start", agent=agent.name,
                            prompt_preview=params.get("prompt", ""))

            prompt = params.get("prompt", "")
            input_file = previous_output_path

            response = await self.provider.call(
                system_prompt=agent.system_prompt,
                user_message=prompt,
                input_file=input_file,
                requirements_file=requirements_file,
                cwd=str(self.context.session_dir),
            )

            previous_output_path = self.context.save_output(agent.name, response.text)
            responses.append(response)

            self.logger.log_complete(agent.name, response)
            self.trace.emit("agent_complete", agent=agent.name,
                            elapsed_seconds=response.elapsed_seconds,
                            output_preview=response.text)
            print(f"  [OK] [{agent.name}] 완료 ({response.elapsed_seconds:.1f}s)")

        total_elapsed = time.time() - total_start
        self.trace.emit("pipeline_end", pattern="sequential",
                        elapsed_seconds=total_elapsed)
        print(f"\n[DONE] Sequential 전체 완료 ({total_elapsed:.1f}s)")

        if responses:
            self.context.save_final_result(responses[-1].text)

        return responses

    async def parallel(
        self,
        tasks: List[Tuple[Agent, Dict]],
        requirements_file: Optional[str] = None,
    ) -> List[LLMResponse]:
        """Parallel 패턴: 에이전트를 동시 실행."""
        print(f"\n>> Parallel 실행 시작 ({len(tasks)}개 에이전트)")
        print(f"  동시 실행: {', '.join(a.name for a, _ in tasks)}\n")
        self.trace.emit("pipeline_start", pattern="parallel",
                        detail=f"{len(tasks)}개 에이전트")

        total_start = time.time()

        async def _run_one(agent: Agent, params: Dict) -> LLMResponse:
            self.logger.log_start(agent.name, "parallel")

            prompt = params.get("prompt", "")
            input_file = params.get("input_file")

            response = await self.provider.call(
                system_prompt=agent.system_prompt,
                user_message=prompt,
                input_file=input_file,
                requirements_file=requirements_file,
                cwd=str(self.context.session_dir),
            )

            self.context.save_output(agent.name, response.text)
            self.logger.log_complete(agent.name, response)
            print(f"  [OK] [{agent.name}] 완료 ({response.elapsed_seconds:.1f}s)")

            return response

        raw_results = await asyncio.gather(
            *[_run_one(agent, params) for agent, params in tasks],
            return_exceptions=True,
        )

        responses: List[LLMResponse] = []
        succeeded: List[Tuple[str, LLMResponse]] = []
        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                print(f"  [FAIL] [{tasks[i][0].name}] 실패: {result}")
                self.logger.log_error(tasks[i][0].name, result)
                self.trace.emit("agent_error", agent=tasks[i][0].name,
                                error=str(result))
            else:
                responses.append(result)
                succeeded.append((tasks[i][0].name, result))

        total_elapsed = time.time() - total_start
        self.trace.emit("pipeline_end", pattern="parallel",
                        elapsed_seconds=total_elapsed)
        print(f"\n[DONE] Parallel 전체 완료 ({total_elapsed:.1f}s)")

        summary = "\n\n---\n\n".join(
            f"## {name}\n\n{r.text}" for name, r in succeeded
        )
        self.context.save_final_result(summary)

        return list(responses)

    async def loop(
        self,
        agent: Agent,
        prompt: str,
        n: int = 3,
        requirements_file: Optional[str] = None,
    ) -> List[LLMResponse]:
        """Loop 패턴: 동일 에이전트가 자신의 출력을 n회 반복 개선."""
        print(f"\n>> Loop 실행 시작 ({agent.name} × {n}회)")
        self.trace.emit("pipeline_start", pattern="loop",
                        detail=f"{agent.name} × {n}회 반복")

        total_start = time.time()
        responses: List[LLMResponse] = []
        previous_output: Optional[str] = None

        for i in range(n):
            self.logger.log_start(agent.name, f"loop_{i+1}")

            if previous_output is None:
                iter_prompt = prompt
            else:
                iter_prompt = (
                    f"다음은 당신이 이전에 생성한 결과물입니다:\n\n"
                    f"---\n{previous_output}\n---\n\n"
                    f"위 결과물을 평가하고 개선해주세요. "
                    f"문제점을 식별하고 더 나은 버전을 작성하세요.\n\n"
                    f"원래 요청: {prompt}"
                )

            self.trace.emit("agent_start", agent=agent.name,
                            prompt_preview=iter_prompt,
                            detail=f"Iteration {i+1}/{n}")

            response = await self.provider.call(
                system_prompt=agent.system_prompt,
                user_message=iter_prompt,
                requirements_file=requirements_file,
                cwd=str(self.context.session_dir),
            )

            previous_output = response.text
            self.context.save_output(f"{agent.name}_iter{i+1}", response.text)
            responses.append(response)
            self.logger.log_complete(agent.name, response)
            self.trace.emit("agent_complete", agent=agent.name,
                            elapsed_seconds=response.elapsed_seconds,
                            output_preview=response.text,
                            detail=f"Iteration {i+1}/{n}")

            print(f"  [OK] [{agent.name}] Iteration {i+1}/{n} 완료 ({response.elapsed_seconds:.1f}s)")

        total_elapsed = time.time() - total_start
        self.trace.emit("pipeline_end", pattern="loop",
                        elapsed_seconds=total_elapsed)
        print(f"\n[DONE] Loop 전체 완료 ({total_elapsed:.1f}s)")

        if responses:
            self.context.save_final_result(responses[-1].text)

        return responses

    async def reactive(
        self,
        agent: Agent,
        ticks: list,
        tick_interval: float = 2.0,
        threshold: int = 20,
    ) -> List[LLMResponse]:
        """Reactive 패턴: Generator가 틱 데이터를 생산, threshold 도달 시 에이전트 분석.

        ticks: 하드코딩된 틱 데이터 리스트 (dict)
        tick_interval: 틱 간 간격 (초)
        threshold: 에이전트를 트리거하는 큐 크기
        """
        print(f"\n>> Reactive 실행 ({agent.name}, {len(ticks)} ticks, threshold={threshold})")
        self.trace.emit("pipeline_start", pattern="reactive",
                        detail=f"Generator → Queue({threshold}) → {agent.name}")

        total_start = time.time()
        queue_buffer: list = []

        # ── Generator Phase: 틱을 하나씩 발행 ──
        for i, tick in enumerate(ticks):
            tick_json = json.dumps(tick, ensure_ascii=False)
            queue_buffer.append(tick)

            self.trace.emit("tick", agent="Generator",
                            detail=f"tick {i + 1}/{len(ticks)}",
                            output_preview=tick_json)

            # threshold 도달 → 분석 트리거
            if len(queue_buffer) >= threshold:
                print(f"  [Observer] Queue threshold 도달 ({len(queue_buffer)}/{threshold}) -에이전트 트리거")
                self.trace.emit("trigger", agent="Observer",
                                detail=f"Queue={len(queue_buffer)}, 에이전트 트리거")

                # 큐 데이터를 프롬프트로 구성
                batch_text = "\n".join(
                    json.dumps(t, ensure_ascii=False) for t in queue_buffer
                )
                analysis_prompt = (
                    f"아래는 최근 수집된 {len(queue_buffer)}개의 주식 틱 데이터입니다.\n\n"
                    f"```json\n{batch_text}\n```\n\n"
                    f"위 데이터를 분석하고 이상 거래를 탐지하세요."
                )

                self.logger.log_start(agent.name, "reactive")
                self.trace.emit("agent_start", agent=agent.name,
                                prompt_preview=analysis_prompt,
                                detail="이상 탐지 분석 시작")

                response = await self.provider.call(
                    system_prompt=agent.system_prompt,
                    user_message=analysis_prompt,
                    cwd=str(self.context.session_dir),
                )

                self.context.save_output(agent.name, response.text)
                self.logger.log_complete(agent.name, response)
                self.trace.emit("agent_complete", agent=agent.name,
                                elapsed_seconds=response.elapsed_seconds,
                                output_preview=response.text,
                                detail="이상 탐지 분석 완료")
                print(f"  [OK] [{agent.name}] 분석 완료 ({response.elapsed_seconds:.1f}s)")

                queue_buffer.clear()

            await asyncio.sleep(tick_interval)

        total_elapsed = time.time() - total_start
        self.trace.emit("pipeline_end", pattern="reactive",
                        elapsed_seconds=total_elapsed)
        print(f"\n[DONE] Reactive 전체 완료 ({total_elapsed:.1f}s)")

        if response:
            self.context.save_final_result(response.text)
            return [response]
        return []

    async def ping_pong(
        self,
        writer: Agent,
        reviewer: Agent,
        prompt: str,
        n: int = 3,
    ) -> List[LLMResponse]:
        """Ping-Pong 패턴: writer(생성) ↔ reviewer(평가)를 n회 반복.

        Round 1: writer가 초안 생성
        Round 2: reviewer가 평가/피드백
        Round 3: writer가 피드백 반영 개선
        ...
        총 2*n회 호출 (writer n번, reviewer n번). 마지막은 항상 writer.
        """
        print(f"\n>> Ping-Pong 실행 ({writer.name} ↔ {reviewer.name}, {n}회)")
        self.trace.emit("pipeline_start", pattern="ping_pong",
                        detail=f"{writer.name} ↔ {reviewer.name} × {n}회")

        total_start = time.time()
        responses: List[LLMResponse] = []
        previous_output: Optional[str] = None
        review_feedback: Optional[str] = None

        for i in range(n):
            round_label = f"Round {i + 1}/{n}"

            # ── Writer 턴 ──
            if i == 0:
                writer_prompt = prompt
            else:
                writer_prompt = (
                    f"다음은 리뷰어의 피드백입니다:\n\n"
                    f"---\n{review_feedback}\n---\n\n"
                    f"위 피드백을 반영하여 결과물을 개선해주세요.\n\n"
                    f"원래 요청: {prompt}"
                )

            self.logger.log_start(writer.name, f"ping_pong_{i + 1}")
            self.trace.emit("agent_start", agent=writer.name,
                            prompt_preview=writer_prompt,
                            detail=f"{round_label} -생성")

            writer_response = await self.provider.call(
                system_prompt=writer.system_prompt,
                user_message=writer_prompt,
                cwd=str(self.context.session_dir),
            )

            previous_output = writer_response.text
            self.context.save_output(f"{writer.name}_round{i + 1}", writer_response.text)
            responses.append(writer_response)
            self.logger.log_complete(writer.name, writer_response)
            self.trace.emit("agent_complete", agent=writer.name,
                            elapsed_seconds=writer_response.elapsed_seconds,
                            output_preview=writer_response.text,
                            detail=f"{round_label} -생성 완료")
            print(f"  [OK] [{writer.name}] {round_label} 생성 ({writer_response.elapsed_seconds:.1f}s)")

            # ── Reviewer 턴 ──
            review_prompt = (
                f"다음은 작성자가 생성한 결과물입니다:\n\n"
                f"---\n{previous_output}\n---\n\n"
                f"위 결과물을 평가해주세요. 구체적인 문제점과 개선 방향을 제시하세요.\n"
                f"좋은 부분도 언급하되, 개선이 필요한 부분에 집중하세요.\n\n"
                f"원래 요청: {prompt}"
            )

            self.logger.log_start(reviewer.name, f"ping_pong_{i + 1}")
            self.trace.emit("agent_start", agent=reviewer.name,
                            prompt_preview=review_prompt,
                            detail=f"{round_label} -평가")

            reviewer_response = await self.provider.call(
                system_prompt=reviewer.system_prompt,
                user_message=review_prompt,
                cwd=str(self.context.session_dir),
            )

            review_feedback = reviewer_response.text
            self.context.save_output(f"{reviewer.name}_round{i + 1}", reviewer_response.text)
            responses.append(reviewer_response)
            self.logger.log_complete(reviewer.name, reviewer_response)
            self.trace.emit("agent_complete", agent=reviewer.name,
                            elapsed_seconds=reviewer_response.elapsed_seconds,
                            output_preview=reviewer_response.text,
                            detail=f"{round_label} -평가 완료")
            print(f"  [OK] [{reviewer.name}] {round_label} 평가 ({reviewer_response.elapsed_seconds:.1f}s)")

        total_elapsed = time.time() - total_start
        self.trace.emit("pipeline_end", pattern="ping_pong",
                        elapsed_seconds=total_elapsed)
        print(f"\n[DONE] Ping-Pong 전체 완료 ({total_elapsed:.1f}s)")

        if responses:
            self.context.save_final_result(responses[-1].text)

        return responses

    @staticmethod
    def _parse_agent_sections(text: str, agent_names: List[str]) -> Dict[str, str]:
        """Master 출력에서 에이전트별 섹션을 파싱.

        ## agent_name 헤더로 구분된 섹션을 추출한다.
        매칭되지 않는 에이전트는 전체 텍스트를 fallback으로 받는다.
        """
        import re
        sections: Dict[str, str] = {}
        # ## agent_name 또는 ## AGENT_NAME 패턴 매칭
        pattern = r"^##\s+(%s)\s*$" % "|".join(re.escape(n) for n in agent_names)
        matches = list(re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE))

        if not matches:
            # 섹션 구분 실패 → 모든 에이전트에게 전체 텍스트 전달
            for name in agent_names:
                sections[name] = text.strip()
            return sections

        for i, match in enumerate(matches):
            name = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections[name] = text[start:end].strip()

        # 매칭 안 된 에이전트는 전체 텍스트 fallback
        for name in agent_names:
            if name not in sections:
                sections[name] = text.strip()

        return sections

    async def master_parallel(
        self,
        user_request: str,
        agent_names: List[str],
    ) -> List[LLMResponse]:
        """Master → Parallel 패턴: Master가 에이전트별 요구사항 생성 후 동시 실행."""
        agents = [self.load_agent(name) for name in agent_names]

        print(f"\n>> Master → Parallel 실행 ({len(agents)}개 에이전트)")
        print(f"  병렬 대상: {', '.join(a.name for a in agents)}\n")
        self.trace.emit("pipeline_start", pattern="parallel",
                        detail=f"Master + {', '.join(a.name for a in agents)}")

        total_start = time.time()

        # ── Step 1: Master가 에이전트별 요구사항 생성 ──
        print("  [Master] 에이전트별 요구사항 생성 중...")
        step_start = time.time()
        self.trace.emit("master_think", agent="Master",
                        prompt_preview="에이전트별 요구사항 생성 중...")

        agent_desc = "\n".join(f"- {a.name}: {a.role}" for a in agents)
        req_prompt = (
            f"사용자 요청: {user_request}\n\n"
            f"아래 에이전트들이 이 요청을 동시에 수행합니다:\n"
            f"{agent_desc}\n\n"
            f"각 에이전트에게 전달할 작업 지시를 에이전트별로 작성하세요.\n"
            f"각 에이전트는 서로의 결과를 볼 수 없으므로, "
            f"독립적으로 작업할 수 있도록 필요한 맥락을 포함하세요.\n\n"
            f"중요: 각 에이전트는 자신의 역할에 해당하는 작업만 수행해야 합니다.\n"
            f"예를 들어 테스트 담당 에이전트에게는 테스트만 작성하라고 지시하고, "
            f"구현 코드를 직접 작성하지 말라고 명시하세요.\n"
            f"구현 담당 에이전트에게는 구현만 작성하라고 지시하세요.\n\n"
            f"반드시 아래 형식으로 출력하세요:\n\n"
            f"## {agents[0].name}\n"
            f"(이 에이전트에게 전달할 구체적 작업 지시)\n\n"
            f"## {agents[1].name if len(agents) > 1 else '...'}\n"
            f"(이 에이전트에게 전달할 구체적 작업 지시)\n\n"
            f"간결하게 작성하세요. 에이전트가 바로 작업에 착수할 수 있는 수준이면 충분합니다."
        )

        req_response = await self.provider.call(
            system_prompt=(
                "당신은 작업을 분배하는 마스터 에이전트입니다. "
                "각 에이전트에게 전달할 작업 지시를 간결하고 명확하게 작성합니다. "
                "불필요한 서론, 성능 요구사항, 비기능 요구사항은 생략하세요. "
                "에이전트가 즉시 작업할 수 있는 핵심 지시만 작성하세요."
            ),
            user_message=req_prompt,
            cwd=str(self.context.session_dir),
        )

        master_elapsed = time.time() - step_start

        # Master 출력을 에이전트별로 파싱
        agent_name_list = [a.name for a in agents]
        sections = self._parse_agent_sections(req_response.text, agent_name_list)

        # 에이전트별 요구사항 파일 저장
        agent_req_paths: Dict[str, str] = {}
        for name, content in sections.items():
            path = self.context.save_agent_requirements(name, content)
            agent_req_paths[name] = path
            print(f"  [Master] requirements_{name}.md 저장 완료")

        # 전체 Master 출력도 보관
        self.context.save_output("Master", req_response.text)
        self.trace.emit("master_think", agent="Master",
                        elapsed_seconds=master_elapsed,
                        output_preview=req_response.text,
                        detail="에이전트별 요구사항 생성 완료")
        print(f"  [Master] 요구사항 분배 완료 ({master_elapsed:.1f}s)")

        # ── Step 2: 에이전트 병렬 실행 (각자의 요구사항 파일 전달) ──
        async def _run_one(agent):
            self.logger.log_start(agent.name, "parallel")
            self.trace.emit("agent_start", agent=agent.name,
                            prompt_preview=user_request)

            response = await self.provider.call(
                system_prompt=agent.system_prompt,
                user_message=user_request,
                requirements_file=agent_req_paths.get(agent.name),
                cwd=str(self.context.session_dir),
            )

            self.context.save_output(agent.name, response.text)
            self.logger.log_complete(agent.name, response)
            self.trace.emit("agent_complete", agent=agent.name,
                            elapsed_seconds=response.elapsed_seconds,
                            output_preview=response.text)
            print(f"  [OK] [{agent.name}] 완료 ({response.elapsed_seconds:.1f}s)")
            return response

        raw_results = await asyncio.gather(
            *[_run_one(a) for a in agents],
            return_exceptions=True,
        )

        responses = []
        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                print(f"  [FAIL] [{agents[i].name}] 실패: {result}")
                self.trace.emit("agent_error", agent=agents[i].name,
                                error=str(result))
            else:
                responses.append(result)

        total_elapsed = time.time() - total_start
        self.trace.emit("pipeline_end", pattern="parallel",
                        elapsed_seconds=total_elapsed)
        print(f"\n[DONE] Master → Parallel 완료 ({total_elapsed:.1f}s)")

        if responses:
            summary = "\n\n---\n\n".join(
                f"## {agents[i].name}\n\n{r.text}"
                for i, r in enumerate(responses)
            )
            self.context.save_final_result(summary)

        return responses

    def copy_tools(self, tools_dir: str = "tools") -> Optional[str]:
        """tools/ 디렉토리를 세션 디렉토리로 복사. 복사된 경로를 반환."""
        src = Path(tools_dir)
        if not src.exists():
            return None
        dst = self.context.session_dir / "tools"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return str(dst)

    async def tool_call(
        self,
        agent: Agent,
        prompt: str,
        tool_descriptions: str,
    ) -> List[LLMResponse]:
        """Tool Calling 패턴: 에이전트가 도구를 사용하여 작업 수행.

        1. tools/ 를 세션 디렉토리에 복사
        2. 에이전트에게 도구 설명 + 사용자 요청 전달
        3. 에이전트가 자체적으로 도구 실행 (Bash 등) 후 응답
        """
        print(f"\n>> Tool Calling 실행 ({agent.name})")
        self.trace.emit("pipeline_start", pattern="tool_call",
                        detail=f"{agent.name} + tools")

        # 도구를 세션 디렉토리로 복사
        tools_path = self.copy_tools()
        if tools_path:
            print(f"  [Tools] 도구 복사 완료: {tools_path}")

        total_start = time.time()

        # 도구 설명을 프롬프트에 포함
        full_prompt = (
            f"[사용 가능한 도구]\n{tool_descriptions}\n\n"
            f"도구는 세션 디렉토리 내 tools/ 폴더에 있습니다.\n"
            f"필요하면 python tools/<파일명>으로 실행하세요.\n\n"
            f"[사용자 요청]\n{prompt}"
        )

        self.logger.log_start(agent.name, "tool_call")
        self.trace.emit("agent_start", agent=agent.name,
                        prompt_preview=full_prompt)

        response = await self.provider.call(
            system_prompt=agent.system_prompt,
            user_message=full_prompt,
            cwd=str(self.context.session_dir),
        )

        self.context.save_output(agent.name, response.text)
        self.logger.log_complete(agent.name, response)
        self.trace.emit("agent_complete", agent=agent.name,
                        elapsed_seconds=response.elapsed_seconds,
                        output_preview=response.text)
        print(f"  [OK] [{agent.name}] 완료 ({response.elapsed_seconds:.1f}s)")

        total_elapsed = time.time() - total_start
        self.trace.emit("pipeline_end", pattern="tool_call",
                        elapsed_seconds=total_elapsed)
        print(f"\n[DONE] Tool Calling 완료 ({total_elapsed:.1f}s)")

        self.context.save_final_result(response.text)
        return [response]

    async def execute_ir(self, task_ir: dict) -> List[LLMResponse]:
        """Task IR을 해석하여 적절한 실행 패턴으로 에이전트를 실행.

        Note: depends_on 필드는 현재 무시됩니다. sequential 실행 시
        tasks 배열 순서대로 실행되며, parallel 실행 시 모두 동시 실행됩니다.
        """
        execution = task_ir["execution"]
        steps = []

        for task in task_ir["tasks"]:
            agent = self.load_agent(task["agent"])
            steps.append((agent, {"prompt": task["prompt"]}))

        requirements_file = self.context.requirements_path

        if execution == "sequential":
            return await self.sequential(steps, requirements_file=requirements_file)
        elif execution == "parallel":
            return await self.parallel(steps, requirements_file=requirements_file)
        else:
            raise ValueError(f"알 수 없는 실행 패턴: {execution}")

    async def run_master(
        self,
        user_request: str,
        agent_names: List[str],
    ) -> List[LLMResponse]:
        """
        Master Agent를 통한 전체 파이프라인 실행 (Iterative 모드).

        각 에이전트 실행 전 Master가 개입하여 작업 지시를 생성한다:
          Master → agent₁ → Master → agent₂ → Master → agent₃ → ... → Master(집계)

        architect가 포함된 경우, architect의 출력을 requirements.md로 저장하여
        이후 모든 에이전트에게 컨텍스트로 전달한다.
        """
        agents = [self.load_agent(name) for name in agent_names]

        # architect가 포함되어 있으면 첫 번째로 이동
        architect_indices = [i for i, a in enumerate(agents) if a.name == "architect"]
        if architect_indices and architect_indices[0] != 0:
            idx = architect_indices[0]
            agents.insert(0, agents.pop(idx))
            print(f"  [Master] 'architect'를 첫 번째 순서로 이동했습니다.")

        print(f"\n>> Master Agent: 반복(iterative) 실행 시작 ({len(agents)}개 에이전트)")
        print(f"  순서: {' -> '.join(a.name for a in agents)}\n")
        self.trace.emit("pipeline_start", pattern="master",
                        detail=f"{len(agents)}개 에이전트: {', '.join(a.name for a in agents)}")

        total_start = time.time()
        responses: List[LLMResponse] = []
        completed: List[Tuple[str, LLMResponse]] = []
        previous_output_path: Optional[str] = None
        task_log: List[dict] = []

        for agent in agents:
            # ── Master 개입: 작업 지시 생성 ──
            print(f"  [Master -> {agent.name}] 작업 지시 생성 중...")
            step_start = time.time()

            task_prompt = await self.master.generate_step_task(
                user_request=user_request,
                target_agent=agent,
                completed_tasks=completed,
                requirements_file=self.context.requirements_path,
            )

            master_elapsed = time.time() - step_start
            self.trace.emit("master_think", agent=agent.name,
                            elapsed_seconds=master_elapsed,
                            prompt_preview=task_prompt)
            print(f"  [Master -> {agent.name}] 작업 지시 완료 ({master_elapsed:.1f}s)")

            # 작업 지시 로그 저장
            task_log.append({
                "agent": agent.name,
                "prompt": task_prompt,
                "master_elapsed": round(master_elapsed, 1),
            })

            # ── 에이전트 실행 ──
            input_file = previous_output_path

            response = await self.run(
                agent=agent,
                prompt=task_prompt,
                input_file=input_file,
                requirements_file=self.context.requirements_path,
            )

            responses.append(response)
            completed.append((agent.name, response))
            previous_output_path = self.context.get_previous_output(agent.name)

            # ── architect 특수 처리: 출력을 요구사항 명세서로 저장 ──
            if agent.name == "architect":
                req_path = self.context.save_requirements(response.text)
                print(f"  [Master] 요구사항 명세서 저장: {req_path}")

        # ── Master 집계 ──
        total_elapsed = time.time() - total_start
        self.trace.emit("pipeline_end", pattern="master",
                        elapsed_seconds=total_elapsed)
        print(f"\n[DONE] Master 전체 완료 ({total_elapsed:.1f}s)")

        # Task IR 형식으로 실행 로그 저장
        self.context.save_task_ir({
            "execution": "master_iterative",
            "tasks": task_log,
        })

        if responses:
            self.context.save_final_result(responses[-1].text)

        return responses
