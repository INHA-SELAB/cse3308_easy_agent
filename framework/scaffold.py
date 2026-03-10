"""
python -m framework init  : 프로젝트 초기화 (환경 검증 + 학생 작업 디렉토리 생성)
python -m framework check : 환경 검증만 실행
"""

import json
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Environment check
# ---------------------------------------------------------------------------

def check(config_path: str = "config.json") -> bool:
    """환경을 검증하고 결과를 출력한다. 모든 항목이 통과하면 True."""
    results = []

    # 1. Python version
    v = sys.version_info
    ok = v >= (3, 10)
    results.append(("Python >= 3.10", ok, f"{v.major}.{v.minor}.{v.micro}"))

    # 2. config.json
    cfg_path = Path(config_path)
    if cfg_path.exists():
        try:
            with open(cfg_path, encoding="utf-8") as f:
                config = json.load(f)
            provider_name = config.get("provider", "claude")
            results.append(("config.json", True, f"provider={provider_name}"))
        except Exception as e:
            results.append(("config.json", False, str(e)))
            config = {}
            provider_name = "claude"
    else:
        results.append(("config.json", False, "파일 없음"))
        config = {}
        provider_name = "claude"

    # 3. CLI tool installed
    provider_cfg = config.get("providers", {}).get(provider_name, {})
    cmd = provider_cfg.get("command", provider_name)
    found = shutil.which(cmd)
    results.append((f"{cmd} CLI 설치", bool(found), found or "PATH에서 찾을 수 없음"))

    # 4. agents directory
    agents_dir = Path(config.get("agents_dir", "agents"))
    if agents_dir.exists():
        jsons = list(agents_dir.glob("*.json"))
        results.append(("agents/ 디렉토리", bool(jsons), f"{len(jsons)}개 에이전트"))
    else:
        results.append(("agents/ 디렉토리", False, "디렉토리 없음"))

    # 5. orchestration directory
    orch_dir = Path("orchestration")
    if orch_dir.exists() and (orch_dir / "pipeline.py").exists():
        results.append(("orchestration/pipeline.py", True, "존재"))
    else:
        results.append(("orchestration/pipeline.py", False, "없음 (python -m framework init 실행)"))

    # Print results
    print()
    print("=" * 55)
    print("  Agent Lab - 환경 검증")
    print("=" * 55)
    all_ok = True
    for name, ok, detail in results:
        mark = "[OK]" if ok else "[!!]"
        print(f"  {mark} {name:<30s} {detail}")
        if not ok:
            all_ok = False
    print("=" * 55)

    if all_ok:
        print("  모든 항목 통과. 준비 완료!")
    else:
        print("  위 [!!] 항목을 해결한 후 다시 실행하세요.")

    print()
    return all_ok


# ---------------------------------------------------------------------------
# Init: scaffold student workspace
# ---------------------------------------------------------------------------

PIPELINE_TEMPLATE = '''\
"""
Agent Lab - 오케스트레이션 파이프라인

이 파일에서 에이전트 조합과 실행 패턴을 설계합니다.

실행 방법:
    python orchestration/pipeline.py single
    python orchestration/pipeline.py sequential
    python orchestration/pipeline.py parallel
    python orchestration/pipeline.py master
"""

import sys
sys.path.insert(0, ".")  # 프로젝트 루트에서 framework를 import하기 위함

from framework import run, sequential, parallel, master, print_trace


# ============================================================================
#  패턴 1: Single Agent
#  - 하나의 에이전트에게 작업을 요청합니다.
#  - 수정 포인트: 에이전트 이름, 프롬프트
# ============================================================================

def run_single():
    print("\\n[패턴 1] Single Agent")
    print("-" * 40)

    result = run("code_writer", "피보나치 함수를 작성하세요")

    print(result.text)
    print(f"\\n소요 시간: {result.elapsed_seconds:.1f}s")
    if result.cost_usd:
        print(f"비용: ${result.cost_usd:.4f}")
    print_trace()


# ============================================================================
#  패턴 2: Sequential Agent
#  - 에이전트들이 순서대로 실행됩니다.
#  - 이전 에이전트의 출력이 다음 에이전트의 입력으로 자동 전달됩니다.
#  - 수정 포인트: 에이전트 순서, 각 에이전트의 프롬프트
# ============================================================================

def run_sequential():
    print("\\n[패턴 2] Sequential Agent")
    print("-" * 40)

    results = sequential([
        ("code_writer",   {"prompt": "피보나치 함수를 작성하세요"}),
        ("code_reviewer", {"prompt": "이전 에이전트의 코드를 리뷰하세요"}),
    ])

    for i, r in enumerate(results):
        print(f"\\n--- 에이전트 {i+1} ({r.elapsed_seconds:.1f}s) ---")
        print(r.text)
    print_trace()


# ============================================================================
#  패턴 3: Parallel Agent
#  - 에이전트들이 동시에 실행됩니다.
#  - 서로 독립적인 작업에 적합합니다.
#  - 수정 포인트: 에이전트 조합, 각 에이전트의 프롬프트
# ============================================================================

def run_parallel():
    print("\\n[패턴 3] Parallel Agent")
    print("-" * 40)

    code = "def fib(n): return fib(n-1) + fib(n-2) if n > 1 else n"

    results = parallel([
        ("code_reviewer", {"prompt": f"이 코드를 리뷰하세요:\\n{code}"}),
        ("test_writer",   {"prompt": f"이 코드의 테스트를 작성하세요:\\n{code}"}),
    ])

    for i, r in enumerate(results):
        print(f"\\n--- 에이전트 {i+1} ({r.elapsed_seconds:.1f}s) ---")
        print(r.text)
    print_trace()


# ============================================================================
#  패턴 4: Master Agent
#  - Master Agent가 자연어 요청을 분석하여 자동으로 작업을 분배합니다.
#  - 수정 포인트: 요청 내용, 사용할 에이전트 목록
# ============================================================================

def run_master():
    print("\\n[패턴 4] Master Agent")
    print("-" * 40)

    results = master(
        "피보나치 함수를 작성하고 리뷰해줘",
        ["code_writer", "code_reviewer"],
    )

    for i, r in enumerate(results):
        print(f"\\n--- 에이전트 {i+1} ({r.elapsed_seconds:.1f}s) ---")
        print(r.text)
    print_trace()


# ============================================================================
#  실행 진입점
# ============================================================================

PATTERNS = {
    "single":     run_single,
    "sequential": run_sequential,
    "parallel":   run_parallel,
    "master":     run_master,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in PATTERNS:
        print("사용법: python orchestration/pipeline.py <pattern>")
        print(f"  patterns: {', '.join(PATTERNS.keys())}")
        sys.exit(1)

    PATTERNS[sys.argv[1]]()
'''


DEFAULT_AGENTS = {
    "code_writer": {
        "name": "code_writer",
        "role": "깔끔하고 효율적인 코드를 작성하는 개발자",
        "system_prompt": (
            "당신은 숙련된 소프트웨어 개발자입니다.\n"
            "주어진 요구사항에 맞는 코드를 작성합니다.\n"
            "- 가독성 좋은 코드 작성\n"
            "- 적절한 주석 포함\n"
            "- 에지 케이스 고려\n"
            "- Python을 기본 언어로 사용\n"
            "\n"
            "요청된 코드를 작성하세요."
        ),
        "output_format": "markdown",
    },
    "code_reviewer": {
        "name": "code_reviewer",
        "role": "코드 품질을 검토하는 시니어 개발자",
        "system_prompt": (
            "당신은 10년 경력의 시니어 개발자입니다.\n"
            "코드 리뷰 시 다음을 중점적으로 확인합니다:\n"
            "- 가독성과 네이밍 컨벤션\n"
            "- 잠재적 버그와 엣지 케이스\n"
            "- 성능 개선 포인트\n"
            "\n"
            "입력된 코드를 분석하고, 리뷰 결과를 작성하세요."
        ),
        "output_format": "markdown",
    },
    "test_writer": {
        "name": "test_writer",
        "role": "테스트 코드를 작성하는 QA 엔지니어",
        "system_prompt": (
            "당신은 숙련된 QA 엔지니어입니다.\n"
            "주어진 코드에 대한 테스트를 작성합니다.\n"
            "- pytest 프레임워크 사용\n"
            "- 정상 케이스와 엣지 케이스 포함\n"
            "- 경계값 테스트 포함\n"
            "- 명확한 테스트 이름 사용\n"
            "\n"
            "입력된 코드에 대한 테스트를 작성하세요."
        ),
        "output_format": "markdown",
    },
}

DEFAULT_CONFIG = {
    "provider": "claude",
    "providers": {
        "claude": {"command": "claude"},
        "gemini": {"command": "gemini"},
        "codex": {
            "command": "codex",
            "subcommand": "exec",
            "flags": [
                "--json",
                "--skip-git-repo-check",
                "--dangerously-bypass-approvals-and-sandbox",
            ],
        },
    },
    "workspace_dir": "./workspace",
    "log_dir": "./logs",
    "agents_dir": "./agents",
    "max_turns": 1,
    "context": {"max_inline_chars": 50000},
}


def init(config_path: str = "config.json"):
    """프로젝트 초기화: 환경 검증 + 학생 작업 디렉토리 생성"""

    print()
    print("=" * 55)
    print("  Agent Lab - 프로젝트 초기화")
    print("=" * 55)

    created = []
    skipped = []

    # 1. config.json
    cfg = Path(config_path)
    if not cfg.exists():
        cfg.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append("config.json")
    else:
        skipped.append("config.json")

    # 2. agents/ directory + default agents
    agents_dir = Path("agents")
    agents_dir.mkdir(exist_ok=True)
    for name, data in DEFAULT_AGENTS.items():
        agent_file = agents_dir / f"{name}.json"
        if not agent_file.exists():
            agent_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            created.append(f"agents/{name}.json")
        else:
            skipped.append(f"agents/{name}.json")

    # 3. orchestration/pipeline.py
    orch_dir = Path("orchestration")
    orch_dir.mkdir(exist_ok=True)
    pipeline_file = orch_dir / "pipeline.py"
    if not pipeline_file.exists():
        pipeline_file.write_text(PIPELINE_TEMPLATE, encoding="utf-8")
        created.append("orchestration/pipeline.py")
    else:
        skipped.append("orchestration/pipeline.py")

    # 4. workspace/, logs/ directories
    for d in ["workspace", "logs"]:
        Path(d).mkdir(exist_ok=True)

    # Print summary
    if created:
        print("  생성된 파일:")
        for f in created:
            print(f"    + {f}")
    if skipped:
        print("  이미 존재 (건너뜀):")
        for f in skipped:
            print(f"    - {f}")

    print("=" * 55)
    print()

    # 5. Run environment check
    ok = check(config_path)

    if ok:
        print("  시작하기:")
        print("    python orchestration/pipeline.py single")
        print()
    return ok
