import asyncio
import json
import time
from typing import Optional
from .base import BaseProvider, LLMResponse
from ..exceptions import ProviderTimeoutError, ProviderCallError


class CodexProvider(BaseProvider):
    """OpenAI Codex CLI를 subprocess로 호출하는 어댑터 (M-002: stdin pipe)"""

    DEFAULT_FLAGS = [
        "--json",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
    ]
    GLOBAL_FLAGS = {"--search"}

    async def call(
        self,
        system_prompt: str,
        user_message: str,
        input_file: Optional[str] = None,
        requirements_file: Optional[str] = None,
        timeout: int = BaseProvider.DEFAULT_TIMEOUT,
        cwd: Optional[str] = None,
    ) -> LLMResponse:
        full_message = self._build_message(system_prompt, user_message, input_file, requirements_file)
        command = self.provider_config.get("_resolved_command") or self.provider_config.get("command") or "codex"
        subcommand = self.provider_config.get("subcommand", "exec")
        global_flags = list(self.provider_config.get("global_flags", []))
        flags, extracted_global_flags = self._split_flags(self._normalized_flags(self.provider_config.get("flags")))
        global_flags.extend(extracted_global_flags)

        start = time.time()

        proc = await asyncio.create_subprocess_exec(
            command,
            *global_flags,
            subcommand,
            *flags,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_message.encode("utf-8")),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise ProviderTimeoutError("codex", timeout)

        elapsed = time.time() - start

        if proc.returncode != 0:
            raise ProviderCallError("codex", stderr.decode("utf-8"))

        text = self._extract_final_message(stdout.decode("utf-8"))

        return LLMResponse(
            text=text,
            provider="codex",
            elapsed_seconds=elapsed,
            cost_usd=None,
            raw={"stdout": stdout.decode("utf-8"), "stderr": stderr.decode("utf-8")},
        )

    def _normalized_flags(self, flags: Optional[list]) -> list[str]:
        normalized = list(flags or self.DEFAULT_FLAGS)
        return [
            "--dangerously-bypass-approvals-and-sandbox"
            if flag == "--yolo"
            else flag
            for flag in normalized
        ]

    def _split_flags(self, flags: list[str]) -> tuple[list[str], list[str]]:
        exec_flags: list[str] = []
        global_flags: list[str] = []

        for flag in flags:
            if flag in self.GLOBAL_FLAGS:
                global_flags.append(flag)
            else:
                exec_flags.append(flag)

        return exec_flags, global_flags

    def _extract_final_message(self, jsonl_output: str) -> str:
        """JSONL 스트림에서 최종 assistant 메시지 추출"""
        last_message = ""
        for line in jsonl_output.strip().split("\n"):
            try:
                event = json.loads(line)
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    last_message = item.get("text", last_message)
                elif event.get("type", "").startswith("item.") and event.get("role") == "assistant":
                    last_message = event.get("content", last_message)
                elif event.get("type") == "turn.completed":
                    last_message = event.get("text", last_message)
            except json.JSONDecodeError:
                continue
        return last_message or jsonl_output
