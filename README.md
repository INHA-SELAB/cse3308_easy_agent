# Agent Lab: Agentic Coding Pipeline GUI

> CSE3308 수업용 멀티 에이전트 파이프라인 교육 프레임워크

학생들이 다양한 에이전트 파이프라인 패턴을 GUI에서 실행하고 관찰할 수 있는 교육 도구입니다.

---

## 빠른 시작

```bash
# 환경 검증
python -m framework check

# GUI 실행
python main.py
```

---

## 프로젝트 구조

```
CSE33080_EasyAgent/
  main.py              # GUI 실행 진입점
  config.json          # 프로바이더 설정
  agents/              # 에이전트 정의 (JSON)
    architect.json
    code_writer.json
    code_reviewer.json
    test_writer.json
    worker.json        # 범용 에이전트 (Loop, Tool Calling)
    analyst.json       # 이상 거래 탐지 전문가 (Reactive)
  tools/               # 도구 스크립트
    random_dice.py     # 주사위 도구 (Tool Calling 탭)
  framework/           # 프레임워크 코어
    __init__.py        # 공개 API
    __main__.py        # CLI (init, check, run, master, gui)
    engine.py          # 실행 엔진 (모든 파이프라인 패턴)
    gui.py             # Tkinter GUI (7탭)
    master.py          # Master Agent
    agent_loader.py    # JSON -> Agent 변환
    providers/         # LLM CLI 어댑터
      claude_adapter.py
      gemini_adapter.py
      codex_adapter.py
    utils/
      file_context.py  # 에이전트 간 파일 컨텍스트
      trace.py         # 실행 트레이스 수집
      logger.py        # JSONL 실행 로그
  workspace/           # 세션별 에이전트 출력 (런타임 생성)
  logs/                # 실행 로그 (런타임 생성)
```

---

## 7개 파이프라인 패턴

GUI에서 탭으로 전환하여 각 패턴을 실행할 수 있습니다.

### 1. Orchestration

Master Agent가 사용자 요청을 분석하여 선택된 에이전트들에게 순차적으로 작업을 분배합니다.

```
Master -> architect -> Master -> code_writer -> Master -> code_reviewer
```

- 에이전트 조합을 자유롭게 선택 가능
- Master가 매 단계마다 작업 지시를 생성

### 2. Sequential

고정된 순서로 에이전트를 실행합니다. 이전 에이전트의 출력이 다음 에이전트의 입력이 됩니다.

```
architect -> code_writer -> code_reviewer
```

### 3. Parallel

Master Agent가 에이전트별 요구사항을 분리 생성한 후, 에이전트들이 동시에 실행됩니다.

```
Master -> [code_writer, test_writer] (동시 실행)
```

- Master가 각 에이전트에게 역할에 맞는 개별 지시를 전달

### 4. Tool Calling

에이전트가 외부 도구(Python 스크립트)를 실행하여 결과를 반환합니다.

```
[고정 프롬프트] -> worker -> tools/random_dice.py
```

- 고정 시나리오: 주사위 5개 던지기
- 도구가 세션 디렉토리에 자동 복사됨

### 5. Self-Refinement (Loop)

동일 에이전트가 자신의 출력을 평가하고 개선하는 작업을 n회 반복합니다.

```
worker -> worker -> worker (자기 개선 반복)
```

- 반복 횟수 조절 가능 (1~10회)

### 6. Ping-Pong

생성자(writer)와 평가자(reviewer)가 번갈아 작업합니다.

```
code_writer -> code_reviewer -> code_writer -> code_reviewer -> ...
```

- 왕복 횟수 조절 가능 (1~10회)
- Self-Refinement과 비교: 외부 평가자가 새로운 관점 제공

### 7. Reactive

Generator가 주기적으로 데이터를 생산하고, Queue에 일정량 쌓이면 에이전트가 분석을 수행합니다.

```
Generator (1초/틱) -> Queue (20개) -> analyst (이상 탐지)
```

- 고정 시나리오: EASY 종목 주식 틱 데이터, 이상 거래 탐지
- 틱 15/17/19에 이상 신호 삽입 (거래량 급등, 가격 급등, 복합)

---

## 에이전트 정의

`agents/` 디렉토리에 JSON 파일로 에이전트를 정의합니다.

```json
{
  "name": "code_reviewer",
  "role": "코드 품질을 검토하는 시니어 개발자",
  "system_prompt": "당신은 10년 경력의 시니어 개발자입니다...",
  "output_format": "markdown"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string | 에이전트 고유 식별자 (영문, snake_case) |
| `role` | string | 에이전트 역할 요약 |
| `system_prompt` | string | LLM에 전달할 시스템 프롬프트 |
| `output_format` | string | `markdown` / `json` / `text` |

---

## 설정 (config.json)

```json
{
  "provider": "claude",
  "workspace_dir": "workspace",
  "log_dir": "logs",
  "agents_dir": "agents"
}
```

### 프로바이더

| 프로바이더 | CLI 명령 | 비용 추적 |
|-----------|---------|----------|
| Claude | `claude -p` | `cost_usd` 지원 |
| Gemini | `gemini -p` | 미지원 |
| Codex | `codex exec` | 미지원 |

GUI 좌측 상단에서 프로바이더를 선택할 수 있습니다.

---

## CLI 사용법

```bash
# 환경 검증
python -m framework check

# GUI 실행
python main.py
python -m framework gui

# 단일 에이전트 실행
python -m framework run code_writer "피보나치 함수를 작성하세요"

# 마스터 에이전트 실행
python -m framework master "함수를 작성하고 리뷰해줘" code_writer code_reviewer

# 프로바이더 지정
python -m framework run code_writer "hello" --provider gemini
```

---

## 세션 출력

각 실행은 `workspace/{session_id}/` 디렉토리에 결과를 저장합니다.

```
workspace/20260310_211611_dee6eb37/
  agent_code_writer_output.md
  agent_test_writer_output.md
  requirements_code_writer.md    # Parallel: 에이전트별 요구사항
  requirements_test_writer.md
  final_result.md
  trace.jsonl                    # 실행 트레이스
```
