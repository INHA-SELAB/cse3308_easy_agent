import asyncio
from typing import List, Optional
from .engine import Engine
from .agent_loader import Agent
from .providers.base import LLMResponse

__all__ = ["Engine", "Agent", "LLMResponse", "run", "sequential", "parallel", "master", "master_parallel", "loop", "tool_call", "ping_pong", "reactive", "print_trace"]

_default_engine: Optional[Engine] = None
_current_provider: Optional[str] = None


def _get_engine(config_path: str = "config.json", provider: Optional[str] = None) -> Engine:
    """기본 엔진 인스턴스를 반환 (provider가 바뀌면 재생성)"""
    global _default_engine, _current_provider
    if _default_engine is None or provider != _current_provider:
        _default_engine = Engine(config_path, provider=provider)
        _current_provider = provider
    return _default_engine


def _run_async(coro):
    """async 함수를 sync 환경에서 실행"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        try:
            import nest_asyncio
        except ImportError:
            from .exceptions import AgentLabError
            raise AgentLabError(
                "Jupyter 환경에서 실행하려면 nest_asyncio가 필요합니다.\n"
                "설치: pip install nest_asyncio"
            )
        nest_asyncio.apply()
        return loop.run_until_complete(coro)
    else:
        return asyncio.run(coro)


def run(
    agent_name: str,
    prompt: str,
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> LLMResponse:
    """단일 에이전트 실행 (sync)."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    agent = engine.load_agent(agent_name)
    result = _run_async(engine.run(agent, prompt=prompt))
    engine.trace.emit("pipeline_end", pattern="single",
                      elapsed_seconds=result.elapsed_seconds)
    return result


def sequential(
    steps: list,
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> List[LLMResponse]:
    """Sequential 패턴 실행 (sync)."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    agent_steps = [
        (engine.load_agent(name), params) for name, params in steps
    ]
    return _run_async(engine.sequential(agent_steps))


def parallel(
    tasks: list,
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> List[LLMResponse]:
    """Parallel 패턴 실행 (sync)."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    agent_tasks = [
        (engine.load_agent(name), params) for name, params in tasks
    ]
    return _run_async(engine.parallel(agent_tasks))


def master(
    user_request: str,
    agent_names: List[str],
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> List[LLMResponse]:
    """Master Agent를 통한 전체 파이프라인 실행 (sync)."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    return _run_async(engine.run_master(user_request, agent_names))


def master_parallel(
    user_request: str,
    agent_names: List[str],
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> List[LLMResponse]:
    """Master → Parallel 패턴 실행 (sync) — Master가 명세 생성 후 에이전트 동시 실행."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    return _run_async(engine.master_parallel(user_request, agent_names))


def loop(
    agent_name: str,
    prompt: str,
    n: int = 3,
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> List[LLMResponse]:
    """Loop 패턴 실행 (sync) — 동일 에이전트가 n회 자기 개선."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    agent = engine.load_agent(agent_name)
    return _run_async(engine.loop(agent, prompt, n=n))


def tool_call(
    agent_name: str,
    prompt: str,
    tool_descriptions: str,
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> List[LLMResponse]:
    """Tool Calling 패턴 실행 (sync) — 에이전트가 도구를 사용하여 작업 수행."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    agent = engine.load_agent(agent_name)
    return _run_async(engine.tool_call(agent, prompt, tool_descriptions))


def reactive(
    agent_name: str,
    ticks: list,
    tick_interval: float = 2.0,
    threshold: int = 20,
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> List[LLMResponse]:
    """Reactive 패턴 실행 (sync) — Generator → Queue → Agent 트리거."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    agent = engine.load_agent(agent_name)
    return _run_async(engine.reactive(agent, ticks, tick_interval=tick_interval, threshold=threshold))


def ping_pong(
    writer_name: str,
    reviewer_name: str,
    prompt: str,
    n: int = 3,
    config_path: str = "config.json",
    provider: Optional[str] = None,
) -> List[LLMResponse]:
    """Ping-Pong 패턴 실행 (sync) — writer ↔ reviewer가 n회 반복."""
    engine = _get_engine(config_path, provider=provider)
    engine.new_session()
    writer = engine.load_agent(writer_name)
    reviewer = engine.load_agent(reviewer_name)
    return _run_async(engine.ping_pong(writer, reviewer, prompt, n=n))


def print_trace(config_path: str = "config.json"):
    """마지막 실행의 트레이스를 출력. 파이프라인 실행 후 호출."""
    engine = _get_engine(config_path)
    engine.trace.print_trace()
