import asyncio
import json
import os
import time
from typing import Optional
from .base import BaseProvider, LLMResponse
from ..exceptions import ProviderTimeoutError, ProviderCallError


class ClaudeProvider(BaseProvider):
    """Claude Code CLI를 subprocess로 호출하는 어댑터 (M-002: stdin pipe)"""

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

        start = time.time()

        # Allow nested claude invocation by clearing CLAUDECODE env var
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        proc = await asyncio.create_subprocess_exec(
            "claude", "-p",
            "--output-format", "json",
            "--max-turns", "25",
            "--dangerously-skip-permissions",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_message.encode("utf-8")),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ProviderTimeoutError("claude", timeout)
        except (asyncio.CancelledError, Exception):
            proc.kill()
            await proc.wait()
            raise

        elapsed = time.time() - start

        if proc.returncode != 0:
            raise ProviderCallError("claude", stderr.decode("utf-8"))

        raw = json.loads(stdout.decode("utf-8"))

        return LLMResponse(
            text=raw.get("result", ""),
            provider="claude",
            elapsed_seconds=elapsed,
            cost_usd=raw.get("cost_usd"),
            raw=raw,
        )
