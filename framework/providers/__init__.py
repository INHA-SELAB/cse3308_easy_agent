import os
import shutil
from .claude_adapter import ClaudeProvider
from .gemini_adapter import GeminiProvider
from .codex_adapter import CodexProvider
from .base import BaseProvider
from ..exceptions import ProviderNotFoundError

_PROVIDERS = {
    "claude": ClaudeProvider,
    "gemini": GeminiProvider,
    "codex": CodexProvider,
}

_CLI_COMMANDS = {
    "claude": "claude",
    "gemini": "gemini",
    "codex": "codex",
}


def _resolve_cli_command(command: str) -> str | None:
    candidates = [command]
    if os.name == "nt" and "." not in os.path.basename(command):
        candidates.extend([f"{command}.cmd", f"{command}.exe", f"{command}.bat"])

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def create_provider(config: dict) -> BaseProvider:
    """설정 딕셔너리를 받아 해당 프로바이더 인스턴스를 반환 (M-004: shutil.which 검증)"""
    provider_name = config.get("provider", "claude")

    if provider_name not in _PROVIDERS:
        raise ValueError(f"지원하지 않는 프로바이더: {provider_name}")

    provider_config = dict(config.get("providers", {}).get(provider_name, {}))
    command = provider_config.get("command") or _CLI_COMMANDS.get(provider_name)
    resolved_command = _resolve_cli_command(command) if command else None

    if command and not resolved_command:
        raise ProviderNotFoundError(provider_name)

    context_config = config.get("context", {})
    max_chars = context_config.get("max_inline_chars", 50000)
    provider_config["_resolved_command"] = resolved_command or command

    return _PROVIDERS[provider_name](
        max_context_chars=max_chars,
        provider_config=provider_config,
    )
