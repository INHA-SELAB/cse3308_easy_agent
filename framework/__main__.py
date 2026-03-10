import sys


def _extract_provider(args: list) -> tuple:
    """인자 리스트에서 --provider 플래그를 추출. (provider, 나머지 인자) 반환."""
    provider = None
    remaining = []
    i = 0
    while i < len(args):
        if args[i] == "--provider" and i + 1 < len(args):
            provider = args[i + 1]
            i += 2
        else:
            remaining.append(args[i])
            i += 1
    return provider, remaining


def main():
    if len(sys.argv) < 2:
        print("Agent Lab Framework")
        print()
        print("사용법:")
        print("  python -m framework init                      프로젝트 초기화")
        print("  python -m framework check                     환경 검증")
        print('  python -m framework run <agent> "<prompt>"    단일 에이전트 실행')
        print('  python -m framework master "<요청>" <agents>  마스터 에이전트 실행')
        print("  python -m framework gui                       GUI 실행")
        print()
        print("옵션:")
        print("  --provider claude|gemini|codex    프로바이더 지정 (기본: config.json)")
        sys.exit(1)

    command = sys.argv[1]

    # --- init / check: no engine needed ---
    if command == "init":
        from .scaffold import init
        ok = init()
        sys.exit(0 if ok else 1)

    if command == "check":
        from .scaffold import check
        ok = check()
        sys.exit(0 if ok else 1)

    if command == "gui":
        from .gui import launch
        launch()
        sys.exit(0)

    # --- run / master: engine needed ---
    provider, args = _extract_provider(sys.argv[2:])
    from . import master, run, print_trace

    if command == "run" and len(args) >= 2:
        agent_name = args[0]
        prompt = args[1]
        result = run(agent_name, prompt, provider=provider)
        print(result.text)
        print_trace()

    elif command == "master" and len(args) >= 2:
        user_request = args[0]
        agent_names = args[1:]
        results = master(user_request, agent_names, provider=provider)
        for r in results:
            print(f"\n{'='*50}")
            print(r.text)
        print_trace()

    elif command in ("run", "master"):
        print(f"'{command}' 명령에 인자가 부족합니다.")
        if command == "run":
            print('  사용법: python -m framework run <agent> "<prompt>" [--provider claude]')
        else:
            print('  사용법: python -m framework master "<요청>" <agent1> <agent2> ... [--provider claude]')
        sys.exit(1)

    else:
        print(f"알 수 없는 명령: {command}")
        print("사용 가능한 명령: init, check, run, master, gui")
        sys.exit(1)


if __name__ == "__main__":
    main()
