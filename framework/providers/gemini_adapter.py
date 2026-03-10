import asyncio
import json
import time
from typing import Optional
from .base import BaseProvider, LLMResponse
from ..exceptions import ProviderTimeoutError, ProviderCallError


class GeminiProvider(BaseProvider):
    """Gemini CLI를 subprocess로 호출하는 어댑터 (M-002: stdin pipe)"""

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

        command = self.provider_config.get("_resolved_command", "gemini")
        proc = await asyncio.create_subprocess_exec(
            command, "-p", " ",
            "--output-format", "json",
            "--yolo",
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
            await proc.wait()
            raise ProviderTimeoutError("gemini", timeout)
        except (asyncio.CancelledError, Exception):
            proc.kill()
            await proc.wait()
            raise

        elapsed = time.time() - start

        if proc.returncode != 0:
            raise ProviderCallError("gemini", stderr.decode("utf-8"))

        raw = json.loads(stdout.decode("utf-8"))

        return LLMResponse(
            text=raw.get("response", ""),
            provider="gemini",
            elapsed_seconds=elapsed,
            cost_usd=None,
            raw=raw,
        )
