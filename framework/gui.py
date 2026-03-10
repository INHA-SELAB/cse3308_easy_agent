"""
Tkinter 기반 파이프라인 교육용 GUI.

레이아웃:
  좌측: 공통 설정 (Provider, Request) + 패턴별 동적 설정 + 실행 버튼 + 로그
  우측: ttk.Notebook 탭 (Orchestration, Self-Refinement, ...) 각각 캔버스 보유
        + 공유 출력 뷰어
"""

import platform
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

_IS_MACOS = platform.system() == "Darwin"


# 노드 상태별 색상
COLOR_IDLE = "#D0D0D0"
COLOR_MASTER_ACTIVE = "#6B9BD2"
COLOR_AGENT_ACTIVE = "#87CEEB"
COLOR_DONE = "#90EE90"
COLOR_ERROR = "#FF6B6B"
COLOR_SHADOW = "#C0C0C0"
COLOR_PULSE_BORDER = "#FF8C00"

# UI 색상
BG_CANVAS = "#FAFAFA"
BG_LOG = "#F5F5F5"
BG_OUTPUT = "#FDFDFD"
COLOR_ACCENT = "#4A90D9"

# 트레이스 이벤트 심볼
EVENT_SYMBOLS = {
    "pipeline_start": ">>",
    "pipeline_end": "<<",
    "master_think": "??",
    "agent_start": "->",
    "agent_complete": "OK",
    "agent_error": "!!",
    "tick": "..",
    "trigger": "!!",
}

AGENTS = ["architect", "code_writer", "test_writer", "code_reviewer"]
PROVIDERS = ["claude", "gemini", "codex"]

# Sequential 패턴: 고정 파이프라인
SEQ_PIPELINE = [
    ("architect", "요구사항을 분석하고 설계 명세를 작성하세요."),
    ("code_writer", "이전 단계의 설계를 기반으로 코드를 작성하세요."),
    ("code_reviewer", "이전 단계의 코드를 리뷰하고 개선사항을 제안하세요."),
]

# Tool Calling 패턴: 도구 설명
# Parallel 패턴: 고정 에이전트
PARALLEL_AGENTS = ["code_writer", "test_writer"]

# Ping-Pong 패턴: 고정 에이전트
PINGPONG_WRITER = "code_writer"
PINGPONG_REVIEWER = "code_reviewer"

TOOL_DESC = """\
- random_dice.py: 1~6짜리 주사위 5개를 던져 결과를 JSON 리스트로 반환
  실행: python tools/random_dice.py
  출력 예시: [3, 1, 5, 2, 6]"""

# Reactive 패턴: 하드코딩 주식 틱 데이터 (20틱, 틱 15/17/19에 이상 삽입)
REACTIVE_AGENT = "analyst"
REACTIVE_THRESHOLD = 20
REACTIVE_TICK_INTERVAL = 1.0
REACTIVE_TICKS = [
    {"tick":  1, "time": "09:00:02", "symbol": "EASY", "price": 50100, "volume": 1523, "change_pct": +0.12},
    {"tick":  2, "time": "09:00:04", "symbol": "EASY", "price": 50080, "volume": 1341, "change_pct": -0.04},
    {"tick":  3, "time": "09:00:06", "symbol": "EASY", "price": 50150, "volume": 2210, "change_pct": +0.14},
    {"tick":  4, "time": "09:00:08", "symbol": "EASY", "price": 50120, "volume": 1876, "change_pct": -0.06},
    {"tick":  5, "time": "09:00:10", "symbol": "EASY", "price": 50200, "volume": 1654, "change_pct": +0.16},
    {"tick":  6, "time": "09:00:12", "symbol": "EASY", "price": 50180, "volume": 2033, "change_pct": -0.04},
    {"tick":  7, "time": "09:00:14", "symbol": "EASY", "price": 50050, "volume": 1490, "change_pct": -0.26},
    {"tick":  8, "time": "09:00:16", "symbol": "EASY", "price": 50070, "volume": 1722, "change_pct": +0.04},
    {"tick":  9, "time": "09:00:18", "symbol": "EASY", "price": 50110, "volume": 1389, "change_pct": +0.08},
    {"tick": 10, "time": "09:00:20", "symbol": "EASY", "price": 50090, "volume": 2540, "change_pct": -0.04},
    {"tick": 11, "time": "09:00:22", "symbol": "EASY", "price": 50130, "volume": 1198, "change_pct": +0.08},
    {"tick": 12, "time": "09:00:24", "symbol": "EASY", "price": 50160, "volume": 1845, "change_pct": +0.06},
    {"tick": 13, "time": "09:00:26", "symbol": "EASY", "price": 50140, "volume": 2105, "change_pct": -0.04},
    {"tick": 14, "time": "09:00:28", "symbol": "EASY", "price": 50100, "volume": 1567, "change_pct": -0.08},
    {"tick": 15, "time": "09:00:30", "symbol": "EASY", "price": 50300, "volume": 18700, "change_pct": +0.40},
    {"tick": 16, "time": "09:00:32", "symbol": "EASY", "price": 50850, "volume": 3102, "change_pct": +1.09},
    {"tick": 17, "time": "09:00:34", "symbol": "EASY", "price": 53800, "volume": 2890, "change_pct": +5.80},
    {"tick": 18, "time": "09:00:36", "symbol": "EASY", "price": 54200, "volume": 3450, "change_pct": +0.74},
    {"tick": 19, "time": "09:00:38", "symbol": "EASY", "price": 56200, "volume": 24100, "change_pct": +3.69},
    {"tick": 20, "time": "09:00:40", "symbol": "EASY", "price": 55800, "volume": 8920, "change_pct": -0.71},
]

LOG_PLACEHOLDER = "  실행 버튼을 눌러 파이프라인을 시작하세요."
OUTPUT_PLACEHOLDER = "  완료된 노드를 클릭하면 에이전트 출력을 확인할 수 있습니다."


class PipelineGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CSE3308 EasyAgent Viewer")
        self.root.geometry("1100x700")
        self.root.minsize(900, 550)

        # Shared state
        self._done = False
        self._running = False
        self._trace_idx = 0
        self._results = None
        self._error = None
        self._engine = None
        self._node_ids: dict = {}
        self._node_colors: dict = {}
        self._node_positions: dict = {}
        self._agent_names: list = []
        self._agent_outputs: dict = {}
        self._agent_elapsed: dict = {}
        self._pulse_nodes: set = set()
        self._pulse_after_id = None
        self._pulse_visible = True
        self._selected_node: str = None
        self._live_edge_ids: list = []
        self._poll_after_id = None
        self._poll_generation = 0
        self._run_generation = 0
        self._last_trace = None

        # Pattern state
        self._current_pattern = "orchestration"
        self._loop_outputs: list = []
        self._interrupted = False
        self._config_widgets: list = []  # 실행 중 비활성화할 위젯들

        self._setup_styles()
        self._build_layout()
        self._build_statusbar()
        self.root.after(100, self._refresh_preview)

    # ── Styles ───────────────────────────────────────────────

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("Accent.TButton",
                        font=("Segoe UI", 10, "bold"))

    # ── Layout ───────────────────────────────────────────────

    def _build_layout(self):
        pw = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True)

        left = self._build_left(pw)
        center = self._build_center(pw)

        pw.add(left, weight=0)
        pw.add(center, weight=1)

    def _build_left(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, width=280)
        frame.pack_propagate(False)

        # Provider (shared)
        ttk.Label(frame, text="Provider 선택",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(12, 2))
        self.provider_var = tk.StringVar(value=PROVIDERS[0])
        self._provider_cb = ttk.Combobox(frame, textvariable=self.provider_var,
                                          values=PROVIDERS, state="readonly")
        self._provider_cb.pack(fill=tk.X, padx=8)
        self._config_widgets.append(self._provider_cb)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(12, 0))

        # Request (shared)
        ttk.Label(frame, text="Request 입력",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(10, 2))
        self.request_text = tk.Text(frame, height=6, wrap=tk.WORD,
                                    font=("Segoe UI", 9),
                                    relief=tk.SOLID, borderwidth=1)
        self.request_text.pack(fill=tk.X, padx=8)
        self.request_text.insert("1.0", "함수를 작성하고 리뷰해주세요")

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(12, 0))

        # Dynamic config container — 패턴별 설정이 여기에 표시됨
        self._config_container = ttk.Frame(frame)
        self._config_container.pack(fill=tk.X, padx=0)

        self._orch_config = self._build_orch_config(self._config_container)
        self._seq_config = self._build_seq_config(self._config_container)
        self._par_config = self._build_parallel_config(self._config_container)
        self._tool_config = self._build_tool_config(self._config_container)
        self._loop_config = self._build_loop_config(self._config_container)
        self._pp_config = self._build_pingpong_config(self._config_container)
        self._react_config = self._build_reactive_config(self._config_container)

        # 초기: Orchestration 설정 표시
        self._orch_config.pack(fill=tk.X)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(8, 0))

        # Run button (single, shared)
        self.run_btn = tk.Button(
            frame, text="\u25b6  실행", command=self._run_pipeline,
            bg=COLOR_ACCENT, fg=COLOR_ACCENT if _IS_MACOS else "white",
            activebackground="#3A7BC8",
            activeforeground="white", font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, cursor="hand2", height=1,
        )
        self.run_btn.pack(fill=tk.X, padx=8, pady=(12, 8))

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(4, 0))

        # Agent Log (shared)
        ttk.Label(frame, text="Agent Log",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(8, 2))
        self.log_text = tk.Text(
            frame, state=tk.DISABLED, wrap=tk.WORD,
            font=("Consolas", 8), bg=BG_LOG,
            relief=tk.SOLID, borderwidth=1,
        )
        log_scroll = ttk.Scrollbar(frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=(0, 4))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=(8, 0), pady=(0, 4))

        self.log_text.tag_configure("sym_start", foreground="#2196F3")
        self.log_text.tag_configure("sym_end", foreground="#4CAF50")
        self.log_text.tag_configure("sym_think", foreground="#FF9800")
        self.log_text.tag_configure("sym_agent", foreground="#2196F3")
        self.log_text.tag_configure("sym_ok", foreground="#4CAF50")
        self.log_text.tag_configure("sym_err", foreground="#F44336")
        self.log_text.tag_configure("sym_tick", foreground="#9E9E9E")
        self.log_text.tag_configure("sym_trigger", foreground="#FF5722")
        self.log_text.tag_configure("placeholder", foreground="#999999")

        self._show_log_placeholder()

        return frame

    def _build_orch_config(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(8, 8))

        ttk.Label(frame, text="에이전트 선택",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self.agent_vars: dict[str, tk.BooleanVar] = {}
        for name in AGENTS:
            var = tk.BooleanVar(value=True)
            self.agent_vars[name] = var
            chk = ttk.Checkbutton(frame, text=name, variable=var,
                                   command=self._refresh_preview)
            chk.pack(anchor="w", padx=8, pady=1)
            self._config_widgets.append(chk)

        return frame

    def _build_seq_config(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(8, 8))

        ttk.Label(frame, text="파이프라인",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        for i, (name, desc) in enumerate(SEQ_PIPELINE):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, padx=8, pady=1)
            ttk.Label(row, text=f"{i + 1}.", font=("Consolas", 9),
                      foreground="#888", width=2).pack(side=tk.LEFT)
            ttk.Label(row, text=name, font=("Consolas", 9, "bold"),
                      foreground="#333").pack(side=tk.LEFT, padx=(2, 0))

        return frame

    def _build_parallel_config(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(8, 8))

        ttk.Label(frame, text="파이프라인",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        # Master
        row_m = ttk.Frame(frame)
        row_m.pack(fill=tk.X, padx=8, pady=1)
        ttk.Label(row_m, text="1.", font=("Consolas", 9),
                  foreground="#888", width=2).pack(side=tk.LEFT)
        ttk.Label(row_m, text="Master", font=("Consolas", 9, "bold"),
                  foreground="#4A90D9").pack(side=tk.LEFT, padx=(2, 0))
        ttk.Label(row_m, text="→ 명세 생성", font=("Segoe UI", 8),
                  foreground="#888").pack(side=tk.LEFT, padx=(4, 0))

        # Parallel agents
        par_label = ttk.Frame(frame)
        par_label.pack(fill=tk.X, padx=8, pady=(4, 1))
        ttk.Label(par_label, text="2.", font=("Consolas", 9),
                  foreground="#888", width=2).pack(side=tk.LEFT)
        ttk.Label(par_label, text="동시 실행:", font=("Segoe UI", 8),
                  foreground="#888").pack(side=tk.LEFT, padx=(2, 0))
        for name in PARALLEL_AGENTS:
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, padx=24, pady=1)
            ttk.Label(row, text=f"• {name}", font=("Consolas", 9, "bold"),
                      foreground="#333").pack(side=tk.LEFT)

        return frame

    def _build_tool_config(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(8, 8))

        ttk.Label(frame, text="에이전트",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self._tool_agent_var = tk.StringVar(value="worker")
        ttk.Label(frame, text="worker  (범용)",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w", padx=8)

        ttk.Label(frame, text="사용 가능 도구",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 4))
        ttk.Label(frame, text="random_dice.py",
                  font=("Consolas", 9), foreground="#2196F3").pack(anchor="w", padx=8)
        ttk.Label(frame, text="주사위 5개 → JSON 리스트",
                  font=("Segoe UI", 8), foreground="#888").pack(anchor="w", padx=8)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(10, 4))
        ttk.Label(frame, text="고정 프롬프트",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(frame, text="\"주사위를 던지고 결과를 알려줘\"",
                  font=("Segoe UI", 8, "italic"), foreground="#666",
                  wraplength=200).pack(anchor="w", padx=8, pady=(2, 0))

        return frame

    def _build_loop_config(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(8, 8))

        ttk.Label(frame, text="에이전트",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self._loop_agent_var = tk.StringVar(value="worker")
        ttk.Label(frame, text="worker  (범용)",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w", padx=8)

        ttk.Label(frame, text="반복 횟수",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 4))
        self._loop_n_var = tk.IntVar(value=3)
        self._loop_n_var.trace_add("write", self._on_loop_n_changed)
        n_frame = ttk.Frame(frame)
        n_frame.pack(fill=tk.X, padx=8)
        self._loop_spinbox = ttk.Spinbox(
            n_frame, from_=1, to=10, textvariable=self._loop_n_var,
            width=5, font=("Segoe UI", 9),
        )
        self._loop_spinbox.pack(side=tk.LEFT)
        ttk.Label(n_frame, text="회", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(4, 0))
        self._config_widgets.append(self._loop_spinbox)

        return frame

    def _build_pingpong_config(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(8, 8))

        ttk.Label(frame, text="에이전트 구성",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(frame, text=f"생성: {PINGPONG_WRITER}",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w", padx=8)
        ttk.Label(frame, text=f"평가: {PINGPONG_REVIEWER}",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w", padx=8)

        ttk.Label(frame, text="왕복 횟수",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 4))
        self._pp_n_var = tk.IntVar(value=3)
        self._pp_n_var.trace_add("write", self._on_pp_n_changed)
        n_frame = ttk.Frame(frame)
        n_frame.pack(fill=tk.X, padx=8)
        self._pp_spinbox = ttk.Spinbox(
            n_frame, from_=1, to=10, textvariable=self._pp_n_var,
            width=5, font=("Segoe UI", 9),
        )
        self._pp_spinbox.pack(side=tk.LEFT)
        ttk.Label(n_frame, text="회", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(4, 0))
        self._config_widgets.append(self._pp_spinbox)

        ttk.Label(frame, text="생성 → 평가 → 개선 → 평가 → ...",
                  font=("Segoe UI", 8), foreground="#888",
                  wraplength=200).pack(anchor="w", padx=8, pady=(8, 0))

        return frame

    def _build_reactive_config(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(8, 8))

        ttk.Label(frame, text="시나리오",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(frame, text="EASY 종목 이상 거래 탐지",
                  font=("Consolas", 9), foreground="#555").pack(anchor="w", padx=8)

        ttk.Label(frame, text="구성",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 4))
        ttk.Label(frame, text=f"Generator: {len(REACTIVE_TICKS)} ticks (1초 간격)",
                  font=("Consolas", 8), foreground="#555").pack(anchor="w", padx=8)
        ttk.Label(frame, text=f"Observer: Queue threshold = {REACTIVE_THRESHOLD}",
                  font=("Consolas", 8), foreground="#555").pack(anchor="w", padx=8)
        ttk.Label(frame, text=f"Agent: {REACTIVE_AGENT}",
                  font=("Consolas", 8), foreground="#555").pack(anchor="w", padx=8)

        ttk.Label(frame, text="Generator → Queue → Agent 트리거",
                  font=("Segoe UI", 8), foreground="#888",
                  wraplength=200).pack(anchor="w", padx=8, pady=(8, 0))

        return frame

    def _build_center(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)

        vpw = ttk.PanedWindow(frame, orient=tk.VERTICAL)
        vpw.pack(fill=tk.BOTH, expand=True)

        # ── 캔버스 노트북 (패턴별 탭) ────────────────────────
        self._canvas_notebook = ttk.Notebook(vpw)
        self._canvas_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Tab 1: Orchestration
        orch_frame = ttk.Frame(self._canvas_notebook)
        self._orch_canvas = tk.Canvas(
            orch_frame, bg=BG_CANVAS,
            highlightthickness=1, highlightbackground="#CCC",
        )
        self._orch_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._orch_canvas.bind("<Configure>", self._on_canvas_resize)
        self._orch_canvas.bind("<Button-1>", self._on_canvas_click)

        # Tab 2: Sequential
        seq_frame = ttk.Frame(self._canvas_notebook)
        self._seq_canvas = tk.Canvas(
            seq_frame, bg=BG_CANVAS,
            highlightthickness=1, highlightbackground="#CCC",
        )
        self._seq_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._seq_canvas.bind("<Configure>", self._on_canvas_resize)
        self._seq_canvas.bind("<Button-1>", self._on_canvas_click)

        # Tab 3: Parallel
        par_frame = ttk.Frame(self._canvas_notebook)
        self._par_canvas = tk.Canvas(
            par_frame, bg=BG_CANVAS,
            highlightthickness=1, highlightbackground="#CCC",
        )
        self._par_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._par_canvas.bind("<Configure>", self._on_canvas_resize)
        self._par_canvas.bind("<Button-1>", self._on_canvas_click)

        # Tab 4: Tool Calling
        tool_frame = ttk.Frame(self._canvas_notebook)
        self._tool_canvas = tk.Canvas(
            tool_frame, bg=BG_CANVAS,
            highlightthickness=1, highlightbackground="#CCC",
        )
        self._tool_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._tool_canvas.bind("<Configure>", self._on_canvas_resize)
        self._tool_canvas.bind("<Button-1>", self._on_canvas_click)

        # Tab 4: Self-Refinement
        loop_frame = ttk.Frame(self._canvas_notebook)
        self._loop_canvas = tk.Canvas(
            loop_frame, bg=BG_CANVAS,
            highlightthickness=1, highlightbackground="#CCC",
        )
        self._loop_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._loop_canvas.bind("<Configure>", self._on_canvas_resize)
        self._loop_canvas.bind("<Button-1>", self._on_canvas_click)

        # Tab 6: Ping-Pong
        pp_frame = ttk.Frame(self._canvas_notebook)
        self._pp_canvas = tk.Canvas(
            pp_frame, bg=BG_CANVAS,
            highlightthickness=1, highlightbackground="#CCC",
        )
        self._pp_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._pp_canvas.bind("<Configure>", self._on_canvas_resize)
        self._pp_canvas.bind("<Button-1>", self._on_canvas_click)

        self._canvas_notebook.add(orch_frame, text="  Orchestration  ")
        self._canvas_notebook.add(seq_frame, text="  Sequential  ")
        self._canvas_notebook.add(par_frame, text="  Parallel  ")
        self._canvas_notebook.add(tool_frame, text="  Tool Calling  ")
        self._canvas_notebook.add(loop_frame, text="  Self-Refinement  ")
        # Tab 7: Reactive
        react_frame = ttk.Frame(self._canvas_notebook)
        self._react_canvas = tk.Canvas(
            react_frame, bg=BG_CANVAS,
            highlightthickness=1, highlightbackground="#CCC",
        )
        self._react_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._react_canvas.bind("<Configure>", self._on_canvas_resize)
        self._react_canvas.bind("<Button-1>", self._on_canvas_click)

        self._canvas_notebook.add(pp_frame, text="  Ping-Pong  ")
        self._canvas_notebook.add(react_frame, text="  Reactive  ")

        # 초기 캔버스 참조
        self.canvas = self._orch_canvas

        # ── 출력 뷰어 (공유) ──────────────────────────────────
        output_frame = ttk.Frame(vpw)
        self._output_header = ttk.Label(output_frame, text="에이전트 출력",
                                         font=("Segoe UI", 9, "bold"))
        self._output_header.pack(anchor="w", padx=8, pady=(4, 2))
        self.output_text = tk.Text(
            output_frame, state=tk.DISABLED, wrap=tk.WORD,
            font=("Consolas", 9), bg=BG_OUTPUT,
            relief=tk.SOLID, borderwidth=1, height=8,
        )
        out_scroll = ttk.Scrollbar(output_frame, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=out_scroll.set)
        out_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=(0, 4))
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=(8, 0), pady=(0, 4))

        self.output_text.tag_configure("placeholder", foreground="#999999")
        self._show_output_placeholder()

        vpw.add(self._canvas_notebook, weight=3)
        vpw.add(output_frame, weight=1)

        return frame

    def _build_statusbar(self):
        self._statusbar = ttk.Label(
            self.root, text="대기 중",
            font=("Segoe UI", 9), relief=tk.SUNKEN, anchor="w",
        )
        self._statusbar.pack(side=tk.BOTTOM, fill=tk.X, padx=0, pady=0)
        self._elapsed_start = None
        self._elapsed_after_id = None

    def _set_status(self, text: str):
        self._statusbar.configure(text=f"  {text}")

    def _start_elapsed_timer(self):
        import time
        self._elapsed_start = time.time()
        self._tick_elapsed()

    def _tick_elapsed(self):
        if self._elapsed_start and self._running:
            import time
            elapsed = time.time() - self._elapsed_start
            m, s = divmod(int(elapsed), 60)
            self._statusbar.configure(text=f"  {self._status_text}  ({m:02d}:{s:02d})")
            self._elapsed_after_id = self.root.after(1000, self._tick_elapsed)

    def _stop_elapsed_timer(self):
        if self._elapsed_after_id:
            self.root.after_cancel(self._elapsed_after_id)
            self._elapsed_after_id = None
        self._elapsed_start = None

    # ── Tab switching ─────────────────────────────────────────

    _TAB_MAP = {
        0: ("orchestration", "_orch_canvas", "_orch_config"),
        1: ("sequential",    "_seq_canvas",  "_seq_config"),
        2: ("parallel",      "_par_canvas",  "_par_config"),
        3: ("tool_call",     "_tool_canvas", "_tool_config"),
        4: ("loop",          "_loop_canvas", "_loop_config"),
        5: ("ping_pong",     "_pp_canvas",   "_pp_config"),
        6: ("reactive",      "_react_canvas","_react_config"),
    }

    def _on_tab_changed(self, event=None):
        idx = self._canvas_notebook.index(self._canvas_notebook.select())

        # 실행 중에는 탭 전환 차단
        if self._running:
            pattern_to_idx = {v[0]: k for k, v in self._TAB_MAP.items()}
            running_idx = pattern_to_idx.get(self._current_pattern, 0)
            if idx != running_idx:
                self._canvas_notebook.select(running_idx)
            return

        # 이전 캔버스 상태 클리어
        self._node_ids.clear()
        self._node_positions.clear()
        self._node_colors.clear()
        self._live_edge_ids.clear()
        self._agent_names = []

        # 모든 config 숨기기
        for _, _, cfg_attr in self._TAB_MAP.values():
            getattr(self, cfg_attr).pack_forget()

        # 선택된 탭의 pattern/canvas/config 활성화
        if idx in self._TAB_MAP:
            pattern, canvas_attr, cfg_attr = self._TAB_MAP[idx]
            self._current_pattern = pattern
            self.canvas = getattr(self, canvas_attr)
            getattr(self, cfg_attr).pack(fill=tk.X)

        # Tool Calling / Reactive 탭: 고정 프롬프트 모드 — Request 입력 비활성화
        if self._current_pattern in ("tool_call", "reactive"):
            self.request_text.configure(state=tk.DISABLED)
        else:
            self.request_text.configure(state=tk.NORMAL)

        self._refresh_preview()

    def _on_loop_n_changed(self, *args):
        """스핀박스 값 변경 시 캔버스 프리뷰 즉시 갱신."""
        if not self._running and self._current_pattern == "loop":
            self._refresh_preview()

    def _on_pp_n_changed(self, *args):
        """Ping-Pong 스핀박스 값 변경 시 캔버스 프리뷰 즉시 갱신."""
        if not self._running and self._current_pattern == "ping_pong":
            self._refresh_preview()

    # ── Placeholder helpers ──────────────────────────────────

    def _show_log_placeholder(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", LOG_PLACEHOLDER, "placeholder")
        self.log_text.configure(state=tk.DISABLED)

    def _show_output_placeholder(self):
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", OUTPUT_PLACEHOLDER, "placeholder")
        self.output_text.configure(state=tk.DISABLED)

    def _show_output(self, agent_name: str, text: str):
        self._output_header.configure(text=f"에이전트 출력 — {agent_name}")
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", text)
        self.output_text.see("1.0")
        self.output_text.configure(state=tk.DISABLED)

    # ── Preview & resize ─────────────────────────────────────

    def _refresh_preview(self):
        if self._running:
            return
        self._node_colors.clear()
        if self._current_pattern == "orchestration":
            selected = [name for name, var in self.agent_vars.items() if var.get()]
            self._draw_dag_orchestration(selected)
        elif self._current_pattern == "sequential":
            self._draw_dag_sequential()
        elif self._current_pattern == "parallel":
            self._draw_dag_parallel()
        elif self._current_pattern == "tool_call":
            self._draw_dag_tool_call()
        elif self._current_pattern == "loop":
            agent = self._loop_agent_var.get()
            self._draw_dag_loop(agent)
        elif self._current_pattern == "ping_pong":
            self._draw_dag_ping_pong()
        elif self._current_pattern == "reactive":
            self._draw_dag_reactive()

    def _on_canvas_resize(self, event=None):
        # 활성 캔버스에서만 리드로
        if event and event.widget != self.canvas:
            return
        if not self._agent_names:
            return
        saved = dict(self._node_colors)
        if self._current_pattern == "orchestration":
            self._draw_dag_orchestration(self._agent_names)
        elif self._current_pattern == "sequential":
            self._draw_dag_sequential()
        elif self._current_pattern == "parallel":
            self._draw_dag_parallel()
        elif self._current_pattern == "tool_call":
            self._draw_dag_tool_call()
        elif self._current_pattern == "loop":
            name = self._agent_names[0] if self._agent_names else ""
            self._draw_dag_loop(name)
        elif self._current_pattern == "ping_pong":
            self._draw_dag_ping_pong()
        elif self._current_pattern == "reactive":
            self._draw_dag_reactive()
        for label, color in saved.items():
            self._set_node_color(label, color)

    # ── Canvas click → show output ───────────────────────────

    def _on_canvas_click(self, event):
        if event.widget != self.canvas:
            return
        items = self.canvas.find_overlapping(event.x - 2, event.y - 2,
                                              event.x + 2, event.y + 2)
        for item in items:
            for label, ids in self._node_ids.items():
                if item in (ids[0], ids[1]):
                    self._select_node(label)
                    return

    def _select_node(self, label: str):
        if self._selected_node and self._selected_node in self._node_ids:
            ids = self._node_ids[self._selected_node]
            self.canvas.itemconfig(ids[0], outline="#888")

        self._selected_node = label
        if label in self._node_ids:
            ids = self._node_ids[label]
            self.canvas.itemconfig(ids[0], outline=COLOR_ACCENT)

        # Loop: 모든 iteration 출력 표시
        if self._current_pattern == "loop" and self._loop_outputs:
            n = len(self._loop_outputs)
            text = ""
            for i, output in enumerate(self._loop_outputs):
                text += f"{'═' * 20} Iteration {i + 1}/{n} {'═' * 20}\n\n"
                text += output + "\n\n"
            self._show_output(label, text.rstrip())
            return

        # Orchestration / fallback
        if label in self._agent_outputs:
            self._show_output(label, self._agent_outputs[label])
        elif label == "Master":
            self._output_header.configure(text="에이전트 출력 — Master")
            self.output_text.configure(state=tk.NORMAL)
            self.output_text.delete("1.0", tk.END)
            self.output_text.insert("1.0", "Master는 각 에이전트에 작업을 지시하는 오케스트레이터입니다.")
            self.output_text.configure(state=tk.DISABLED)
        else:
            self._output_header.configure(text=f"에이전트 출력 — {label}")
            self.output_text.configure(state=tk.NORMAL)
            self.output_text.delete("1.0", tk.END)
            if self._running:
                self.output_text.insert("1.0", "실행 대기 중...")
            else:
                self.output_text.insert("1.0", "출력이 없습니다.")
            self.output_text.configure(state=tk.DISABLED)

    # ── Canvas Drawing (shared) ───────────────────────────────

    def _draw_node(self, c: tk.Canvas, label: str, x: float, y: float,
                   w: int, h: int, color: str, sub_text: str = None):
        r = 10
        x0, y0 = x - w // 2, y - h // 2
        x1, y1 = x + w // 2, y + h // 2

        self._round_rect(c, x0 + 3, y0 + 3, x1 + 3, y1 + 3, r,
                         fill=COLOR_SHADOW, outline="")

        rect = self._round_rect(c, x0, y0, x1, y1, r,
                                fill=color, outline="#888")

        if sub_text:
            text = c.create_text(x, y - 7, text=label,
                                 font=("Segoe UI", 9, "bold"))
            sub = c.create_text(x, y + 10, text=sub_text,
                                font=("Consolas", 8), fill="#555")
        else:
            text = c.create_text(x, y, text=label,
                                 font=("Segoe UI", 9, "bold"))
            sub = None

        self._node_ids[label] = (rect, text, sub)
        self._node_positions[label] = (x, y)

    def _round_rect(self, c: tk.Canvas, x0, y0, x1, y1, r, **kw):
        points = [
            x0 + r, y0,   x1 - r, y0,   x1, y0,   x1, y0 + r,
            x1, y1 - r,   x1, y1,        x1 - r, y1,
            x0 + r, y1,   x0, y1,        x0, y1 - r,
            x0, y0 + r,   x0, y0,        x0 + r, y0,
        ]
        return c.create_polygon(points, smooth=True, **kw)

    def _draw_arrow(self, c: tk.Canvas, x0, y0, x1, y1,
                    color="#666", dash=None, width=2):
        kw = dict(arrow=tk.LAST, fill=color, width=width)
        if dash:
            kw["dash"] = dash
        return c.create_line(x0, y0, x1, y1, **kw)

    # ── Canvas: Orchestration DAG ─────────────────────────────

    def _draw_dag_orchestration(self, agent_names: list):
        self.canvas.delete("all")
        self._node_ids.clear()
        self._node_colors.clear()
        self._node_positions.clear()
        self._live_edge_ids.clear()
        self._agent_names = agent_names

        c = self.canvas
        c.update_idletasks()
        cw = c.winfo_width() or 500
        ch = c.winfo_height() or 400

        node_w, node_h = 110, 40
        n = len(agent_names)

        mx, my = 90, ch // 2
        self._draw_node(c, "Master", mx, my, node_w, node_h, COLOR_IDLE)

        if n == 0:
            return

        spacing = min(80, (ch - 60) / max(n, 1))
        start_y = ch // 2 - (n - 1) * spacing / 2
        ax = cw - 150

        for i, name in enumerate(agent_names):
            ay = start_y + i * spacing
            elapsed = self._agent_elapsed.get(name)
            self._draw_node(c, name, ax, ay, node_w, node_h, COLOR_IDLE,
                            sub_text=f"{elapsed:.1f}s" if elapsed is not None else None)

    # ── Canvas: Sequential DAG ──────────────────────────────

    def _draw_dag_sequential(self):
        self.canvas.delete("all")
        self._node_ids.clear()
        self._node_colors.clear()
        self._node_positions.clear()
        self._live_edge_ids.clear()

        names = [name for name, _ in SEQ_PIPELINE]
        self._agent_names = names

        c = self.canvas
        c.update_idletasks()
        cw = c.winfo_width() or 500
        ch = c.winfo_height() or 400

        n = len(names)
        node_w, node_h = 120, 44
        total_w = n * node_w + (n - 1) * 60
        start_x = (cw - total_w) / 2 + node_w / 2
        cy = ch // 2

        for i, name in enumerate(names):
            nx = start_x + i * (node_w + 60)
            elapsed = self._agent_elapsed.get(name)
            self._draw_node(c, name, nx, cy, w=node_w, h=node_h,
                            color=COLOR_IDLE,
                            sub_text=f"{elapsed:.1f}s" if elapsed is not None else None)

            # 화살표 (노드 간)
            if i > 0:
                prev_x = start_x + (i - 1) * (node_w + 60)
                self._draw_arrow(c,
                                 prev_x + node_w // 2 + 4, cy,
                                 nx - node_w // 2 - 4, cy,
                                 color="#AAA", width=2)

    # ── Canvas: Parallel DAG ────────────────────────────────

    def _draw_dag_parallel(self):
        self.canvas.delete("all")
        self._node_ids.clear()
        self._node_colors.clear()
        self._node_positions.clear()
        self._live_edge_ids.clear()
        self._agent_names = list(PARALLEL_AGENTS)

        c = self.canvas
        c.update_idletasks()
        cw = c.winfo_width() or 500
        ch = c.winfo_height() or 400

        node_w, node_h = 120, 44
        n = len(PARALLEL_AGENTS)

        # Master: 좌측
        mx, my = 100, ch // 2
        self._draw_node(c, "Master", mx, my, node_w, node_h, COLOR_IDLE)

        # Agent 노드: 우측 세로 정렬
        spacing = min(80, (ch - 60) / max(n, 1))
        start_y = ch // 2 - (n - 1) * spacing / 2
        ax = cw - 160

        for i, name in enumerate(PARALLEL_AGENTS):
            ay = start_y + i * spacing
            elapsed = self._agent_elapsed.get(name)
            self._draw_node(c, name, ax, ay, node_w, node_h, COLOR_IDLE,
                            sub_text=f"{elapsed:.1f}s" if elapsed is not None else None)

            # Master → agent 정적 화살표
            self._draw_arrow(c,
                             mx + node_w // 2 + 4, my,
                             ax - node_w // 2 - 4, ay,
                             color="#AAA", width=2)

    # ── Canvas: Tool Calling DAG ────────────────────────────

    def _draw_dag_tool_call(self):
        self.canvas.delete("all")
        self._node_ids.clear()
        self._node_colors.clear()
        self._node_positions.clear()
        self._live_edge_ids.clear()
        self._agent_names = ["worker"]

        c = self.canvas
        c.update_idletasks()
        cw = c.winfo_width() or 500
        ch = c.winfo_height() or 400

        node_w, node_h = 130, 44
        cx, cy = cw // 2, ch // 2

        # 에이전트 노드 (좌측)
        ax = cx - 100
        self._draw_node(c, "worker", ax, cy, node_w, node_h, COLOR_IDLE)

        # 도구 노드 (우측, 다른 스타일)
        tx = cx + 100
        self._draw_tool_node(c, "random_dice", tx, cy, node_w, node_h)

        # 양방향 화살표 (요청/응답)
        gap = 8
        self._draw_arrow(c, ax + node_w // 2 + gap, cy - 6,
                         tx - node_w // 2 - gap, cy - 6,
                         color="#AAA", width=2)
        self._draw_arrow(c, tx - node_w // 2 - gap, cy + 6,
                         ax + node_w // 2 + gap, cy + 6,
                         color="#AAA", width=2, dash=(4, 3))

    def _draw_tool_node(self, c: tk.Canvas, label: str, x: float, y: float,
                        w: int, h: int):
        """도구 노드 — 점선 테두리 + 도구 아이콘 색상."""
        r = 10
        x0, y0 = x - w // 2, y - h // 2
        x1, y1 = x + w // 2, y + h // 2

        self._round_rect(c, x0 + 3, y0 + 3, x1 + 3, y1 + 3, r,
                         fill=COLOR_SHADOW, outline="")

        rect = self._round_rect(c, x0, y0, x1, y1, r,
                                fill="#FFF3E0", outline="#FF9800")

        text = c.create_text(x, y - 7, text=label,
                             font=("Consolas", 9, "bold"), fill="#E65100")
        sub = c.create_text(x, y + 10, text="tool",
                            font=("Consolas", 8), fill="#999")

        self._node_ids[label] = (rect, text, sub)
        self._node_positions[label] = (x, y)

    # ── Canvas: Loop (Self-Refinement) DAG ────────────────────

    def _draw_dag_loop(self, agent_name: str):
        self.canvas.delete("all")
        self._node_ids.clear()
        self._node_colors.clear()
        self._node_positions.clear()
        self._live_edge_ids.clear()
        self._agent_names = [agent_name] if agent_name else []

        c = self.canvas
        c.update_idletasks()
        cw = c.winfo_width() or 500
        ch = c.winfo_height() or 400

        if not agent_name:
            return

        node_w, node_h = 140, 50
        cx, cy = cw // 2, ch // 2

        self._draw_node(c, agent_name, cx, cy, node_w, node_h, COLOR_IDLE)

        # 루프 화살표
        self._draw_loop_arrow(c, cx, cy, node_w, node_h, color="#BBBBBB")

        # 반복 횟수 표시
        try:
            n = self._loop_n_var.get()
        except (tk.TclError, ValueError):
            n = 3
        c.create_text(cx, cy - node_h // 2 - 55, text=f"\u00d7 {n}",
                      font=("Segoe UI", 11, "bold"), fill="#888")

    def _draw_loop_arrow(self, c: tk.Canvas, cx, cy, nw, nh,
                         color="#BBBBBB", width=2):
        half_w = nw // 2
        half_h = nh // 2
        points = [
            cx + half_w - 10, cy - half_h,
            cx + half_w + 15, cy - half_h - 20,
            cx + half_w + 5,  cy - half_h - 40,
            cx,               cy - half_h - 45,
            cx - half_w - 5,  cy - half_h - 40,
            cx - half_w - 15, cy - half_h - 20,
            cx - half_w + 10, cy - half_h,
        ]
        c.create_line(*points, smooth=True, arrow=tk.FIRST,
                      fill=color, width=width)

    def _show_active_loop_arrow(self, agent_name: str, color="#4A90D9"):
        pos = self._node_positions.get(agent_name)
        if not pos:
            return
        cx, cy = pos
        nw, nh = 140, 50
        half_w = nw // 2
        half_h = nh // 2
        points = [
            cx + half_w - 10, cy - half_h,
            cx + half_w + 15, cy - half_h - 20,
            cx + half_w + 5,  cy - half_h - 40,
            cx,               cy - half_h - 45,
            cx - half_w - 5,  cy - half_h - 40,
            cx - half_w - 15, cy - half_h - 20,
            cx - half_w + 10, cy - half_h,
        ]
        aid = self.canvas.create_line(*points, smooth=True, arrow=tk.FIRST,
                                       fill=color, width=3)
        self._live_edge_ids.append(aid)

    def _draw_dag_ping_pong(self):
        """Ping-Pong: writer(좌) ↔ reviewer(우) + 왕복 화살표 + 횟수 표시."""
        self.canvas.delete("all")
        self._node_ids.clear()
        self._node_colors.clear()
        self._node_positions.clear()
        self._live_edge_ids.clear()
        self._agent_names = [PINGPONG_WRITER, PINGPONG_REVIEWER]

        c = self.canvas
        c.update_idletasks()
        cw = c.winfo_width() or 500
        ch = c.winfo_height() or 400

        node_w, node_h = 130, 50
        gap = 120
        cy = ch // 2
        left_x = cw // 2 - gap
        right_x = cw // 2 + gap

        self._draw_node(c, PINGPONG_WRITER, left_x, cy, node_w, node_h, COLOR_IDLE)
        self._draw_node(c, PINGPONG_REVIEWER, right_x, cy, node_w, node_h, COLOR_IDLE)

        # 정적 왕복 화살표: writer → reviewer (위쪽), reviewer → writer (아래쪽)
        arrow_gap = 12
        # 위쪽 화살표: writer → reviewer
        self._draw_arrow(c,
                         left_x + node_w // 2 + 4, cy - arrow_gap,
                         right_x - node_w // 2 - 4, cy - arrow_gap,
                         color="#BBBBBB", width=2)
        # 아래쪽 화살표: reviewer → writer
        self._draw_arrow(c,
                         right_x - node_w // 2 - 4, cy + arrow_gap,
                         left_x + node_w // 2 + 4, cy + arrow_gap,
                         color="#BBBBBB", width=2)

        # 위쪽 라벨: "생성"
        c.create_text(cw // 2, cy - arrow_gap - 14, text="생성",
                      font=("Segoe UI", 8), fill="#999")
        # 아래쪽 라벨: "피드백"
        c.create_text(cw // 2, cy + arrow_gap + 14, text="피드백",
                      font=("Segoe UI", 8), fill="#999")

        # 왕복 횟수 표시
        try:
            n = self._pp_n_var.get()
        except (tk.TclError, ValueError):
            n = 3
        c.create_text(cw // 2, cy - node_h // 2 - 40, text=f"\u00d7 {n}",
                      font=("Segoe UI", 11, "bold"), fill="#888")

    def _draw_dag_reactive(self):
        """Reactive: Generator(좌) → Queue(중앙) → Agent(우)."""
        self.canvas.delete("all")
        self._node_ids.clear()
        self._node_colors.clear()
        self._node_positions.clear()
        self._live_edge_ids.clear()
        self._agent_names = ["Generator", "Observer", REACTIVE_AGENT]

        c = self.canvas
        c.update_idletasks()
        cw = c.winfo_width() or 500
        ch = c.winfo_height() or 400

        node_w, node_h = 120, 50
        cy = ch // 2
        gap = cw // 4

        gen_x = gap
        obs_x = cw // 2
        agent_x = cw - gap

        self._draw_node(c, "Generator", gen_x, cy, node_w, node_h, COLOR_IDLE)

        # Observer는 큐 형태로 표현 (다른 색상)
        self._draw_node(c, "Observer", obs_x, cy, node_w, node_h, "#FFF3E0")

        self._draw_node(c, REACTIVE_AGENT, agent_x, cy, node_w, node_h, COLOR_IDLE)

        # 정적 화살표: Generator → Observer
        self._draw_arrow(c,
                         gen_x + node_w // 2 + 4, cy,
                         obs_x - node_w // 2 - 4, cy,
                         color="#BBBBBB", width=2)

        # 정적 화살표: Observer → Agent (점선 — 조건부 트리거)
        self._draw_arrow(c,
                         obs_x + node_w // 2 + 4, cy,
                         agent_x - node_w // 2 - 4, cy,
                         color="#BBBBBB", width=2, dash=(6, 3))

        # 큐 카운터 표시
        c.create_text(obs_x, cy + node_h // 2 + 18,
                      text=f"threshold = {REACTIVE_THRESHOLD}",
                      font=("Consolas", 8), fill="#999")

        # 트리거 조건 라벨
        c.create_text((obs_x + agent_x) // 2, cy - 20,
                      text="Queue full → trigger",
                      font=("Segoe UI", 8), fill="#999")

    # ── Live Edge ─────────────────────────────────────────────

    def _clear_live_edges(self):
        for item_id in self._live_edge_ids:
            self.canvas.delete(item_id)
        self._live_edge_ids.clear()

    def _show_live_edge(self, from_label: str, to_label: str,
                        color="#4A90D9", dash=None):
        self._clear_live_edges()

        from_pos = self._node_positions.get(from_label)
        to_pos = self._node_positions.get(to_label)
        if not from_pos or not to_pos:
            return

        node_w = 55
        fx, fy = from_pos
        tx, ty = to_pos

        if fx < tx:
            x0, x1 = fx + node_w, tx - node_w
        else:
            x0, x1 = fx - node_w, tx + node_w

        edge_id = self._draw_arrow(self.canvas, x0, fy, x1, ty,
                                    color=color, dash=dash, width=3)
        self._live_edge_ids.append(edge_id)

    def _set_node_color(self, label: str, color: str):
        ids = self._node_ids.get(label)
        if ids:
            self.canvas.itemconfig(ids[0], fill=color)
            self._node_colors[label] = color

    def _set_node_subtext(self, label: str, text: str):
        ids = self._node_ids.get(label)
        if not ids:
            return
        rect_id, text_id, sub_id = ids
        pos = self._node_positions.get(label)
        if not pos:
            return
        x, y = pos

        if sub_id:
            self.canvas.itemconfig(sub_id, text=text)
        else:
            self.canvas.coords(text_id, x, y - 7)
            sub_id = self.canvas.create_text(x, y + 10, text=text,
                                              font=("Consolas", 8), fill="#555")
            self._node_ids[label] = (rect_id, text_id, sub_id)

    # ── Pulse animation ──────────────────────────────────────

    def _start_pulse(self, label: str):
        self._pulse_nodes.add(label)
        if not self._pulse_after_id:
            self._pulse_visible = True
            self._do_pulse()

    def _stop_pulse(self, label: str = None):
        if label:
            self._pulse_nodes.discard(label)
            if label in self._node_ids:
                ids = self._node_ids[label]
                outline = COLOR_ACCENT if label == self._selected_node else "#888"
                self.canvas.itemconfig(ids[0], outline=outline)
            if not self._pulse_nodes and self._pulse_after_id:
                self.root.after_cancel(self._pulse_after_id)
                self._pulse_after_id = None
        else:
            for node in list(self._pulse_nodes):
                if node in self._node_ids:
                    ids = self._node_ids[node]
                    outline = COLOR_ACCENT if node == self._selected_node else "#888"
                    self.canvas.itemconfig(ids[0], outline=outline)
            self._pulse_nodes.clear()
            if self._pulse_after_id:
                self.root.after_cancel(self._pulse_after_id)
                self._pulse_after_id = None

    def _do_pulse(self):
        if not self._pulse_nodes:
            self._pulse_after_id = None
            return
        for node in list(self._pulse_nodes):
            if node not in self._node_ids:
                continue
            ids = self._node_ids[node]
            if self._pulse_visible:
                self.canvas.itemconfig(ids[0], outline=COLOR_PULSE_BORDER)
            else:
                self.canvas.itemconfig(ids[0], outline="#888")
        self._pulse_visible = not self._pulse_visible
        self._pulse_after_id = self.root.after(500, self._do_pulse)

    # ── Config enable/disable ────────────────────────────────

    def _set_config_enabled(self, enabled: bool):
        """좌측 설정 위젯들을 활성/비활성화."""
        state = "readonly" if enabled else "disabled"
        for w in self._config_widgets:
            try:
                w.configure(state=state)
            except tk.TclError:
                try:
                    w.configure(state=tk.NORMAL if enabled else tk.DISABLED)
                except tk.TclError:
                    pass
        # Request text
        self.request_text.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    # ── Pipeline Execution (dispatch) ─────────────────────────

    def _run_pipeline(self):
        if self._running:
            return
        if self._current_pattern == "orchestration":
            self._run_orchestration()
        elif self._current_pattern == "sequential":
            self._run_sequential()
        elif self._current_pattern == "parallel":
            self._run_parallel()
        elif self._current_pattern == "tool_call":
            self._run_tool_call()
        elif self._current_pattern == "loop":
            self._run_loop()
        elif self._current_pattern == "ping_pong":
            self._run_ping_pong()
        elif self._current_pattern == "reactive":
            self._run_reactive()

    def _reset_state(self):
        self._run_generation += 1
        self._done = False
        self._running = True
        self._interrupted = False
        self._trace_idx = 0
        self._results = None
        self._error = None
        self._engine = None
        self._agent_outputs.clear()
        self._agent_elapsed.clear()
        self._loop_outputs.clear()
        self._selected_node = None
        # 설정 비활성화 + 버튼을 중단으로 변경
        self._set_config_enabled(False)
        self.run_btn.configure(
            text="\u25a0  중단", command=self._interrupt_pipeline,
            bg="#D9534F", fg="#D9534F" if _IS_MACOS else "white",
            activebackground="#C9302C",
            state=tk.NORMAL,
        )
        self._stop_pulse()
        self._show_log_placeholder()
        self._show_output_placeholder()
        self._status_text = "파이프라인 실행 중..."
        self._set_status(self._status_text)
        self._start_elapsed_timer()

    def _interrupt_pipeline(self):
        """실행 중인 파이프라인을 중단."""
        self._interrupted = True
        self._done = True
        if self._engine:
            self._engine.cancel()
        self._status_text = "중단 중..."
        self._set_status(self._status_text)

    # ── Orchestration ─────────────────────────────────────────

    def _run_orchestration(self):
        selected = [name for name, var in self.agent_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning("경고", "에이전트를 하나 이상 선택하세요.")
            return
        request = self.request_text.get("1.0", tk.END).strip()
        if not request:
            messagebox.showwarning("경고", "요청을 입력하세요.")
            return

        provider = self.provider_var.get()
        self._reset_state()
        self._draw_dag_orchestration(selected)

        thread = threading.Thread(
            target=self._execute_orchestration,
            args=(request, selected, provider),
            daemon=True,
        )
        thread.start()
        self._poll_trace()

    def _execute_orchestration(self, request: str, agents: list, provider: str):
        gen = self._run_generation
        try:
            from . import _get_engine, master
            self._engine = _get_engine(provider=provider)
            self._results = master(request, agents, provider=provider)
        except Exception as e:
            if gen == self._run_generation:
                self._error = str(e)
        finally:
            if gen == self._run_generation:
                self._done = True

    # ── Sequential ─────────────────────────────────────────────

    def _run_sequential(self):
        request = self.request_text.get("1.0", tk.END).strip()
        if not request:
            messagebox.showwarning("경고", "요청을 입력하세요.")
            return

        provider = self.provider_var.get()
        self._reset_state()
        self._draw_dag_sequential()

        # 첫 에이전트에 사용자 요청을, 나머지는 고정 프롬프트
        steps = []
        for i, (name, default_prompt) in enumerate(SEQ_PIPELINE):
            prompt = request if i == 0 else default_prompt
            steps.append((name, {"prompt": prompt}))

        thread = threading.Thread(
            target=self._execute_sequential,
            args=(steps, provider),
            daemon=True,
        )
        thread.start()
        self._poll_trace()

    def _execute_sequential(self, steps: list, provider: str):
        gen = self._run_generation
        try:
            from . import _get_engine, sequential
            self._engine = _get_engine(provider=provider)
            self._results = sequential(steps, provider=provider)
        except Exception as e:
            if gen == self._run_generation:
                self._error = str(e)
        finally:
            if gen == self._run_generation:
                self._done = True

    # ── Parallel ──────────────────────────────────────────────

    def _run_parallel(self):
        request = self.request_text.get("1.0", tk.END).strip()
        if not request:
            messagebox.showwarning("경고", "요청을 입력하세요.")
            return

        provider = self.provider_var.get()
        self._reset_state()
        self._draw_dag_parallel()

        thread = threading.Thread(
            target=self._execute_parallel,
            args=(request, provider),
            daemon=True,
        )
        thread.start()
        self._poll_trace()

    def _execute_parallel(self, request: str, provider: str):
        gen = self._run_generation
        try:
            from . import _get_engine, master_parallel
            self._engine = _get_engine(provider=provider)
            self._results = master_parallel(request, PARALLEL_AGENTS, provider=provider)
        except Exception as e:
            if gen == self._run_generation:
                self._error = str(e)
        finally:
            if gen == self._run_generation:
                self._done = True

    # ── Tool Calling ──────────────────────────────────────────

    def _run_tool_call(self):
        # 고정 프롬프트 — 사용자 입력 불필요
        request = "주사위를 던지고 결과를 알려줘"
        provider = self.provider_var.get()
        self._reset_state()
        self._draw_dag_tool_call()

        thread = threading.Thread(
            target=self._execute_tool_call,
            args=(request, provider),
            daemon=True,
        )
        thread.start()
        self._poll_trace()

    def _execute_tool_call(self, request: str, provider: str):
        gen = self._run_generation
        try:
            from . import _get_engine, tool_call
            self._engine = _get_engine(provider=provider)
            self._results = tool_call("worker", request, TOOL_DESC, provider=provider)
        except Exception as e:
            if gen == self._run_generation:
                self._error = str(e)
        finally:
            if gen == self._run_generation:
                self._done = True

    # ── Loop (Self-Refinement) ────────────────────────────────

    def _run_loop(self):
        agent_name = self._loop_agent_var.get()
        if not agent_name:
            messagebox.showwarning("경고", "에이전트를 선택하세요.")
            return
        request = self.request_text.get("1.0", tk.END).strip()
        if not request:
            messagebox.showwarning("경고", "요청을 입력하세요.")
            return

        try:
            n = self._loop_n_var.get()
        except (tk.TclError, ValueError):
            n = 3

        provider = self.provider_var.get()
        self._reset_state()
        self._draw_dag_loop(agent_name)

        thread = threading.Thread(
            target=self._execute_loop,
            args=(request, agent_name, n, provider),
            daemon=True,
        )
        thread.start()
        self._poll_trace()

    def _execute_loop(self, request: str, agent_name: str, n: int, provider: str):
        gen = self._run_generation
        try:
            from . import _get_engine, loop
            self._engine = _get_engine(provider=provider)
            self._results = loop(agent_name, request, n=n, provider=provider)
        except Exception as e:
            if gen == self._run_generation:
                self._error = str(e)
        finally:
            if gen == self._run_generation:
                self._done = True

    # ── Ping-Pong ──────────────────────────────────────────────

    def _run_ping_pong(self):
        request = self.request_text.get("1.0", tk.END).strip()
        if not request:
            messagebox.showwarning("경고", "요청을 입력하세요.")
            return

        try:
            n = self._pp_n_var.get()
        except (tk.TclError, ValueError):
            n = 3

        provider = self.provider_var.get()
        self._reset_state()
        self._draw_dag_ping_pong()

        thread = threading.Thread(
            target=self._execute_ping_pong,
            args=(request, n, provider),
            daemon=True,
        )
        thread.start()
        self._poll_trace()

    def _execute_ping_pong(self, request: str, n: int, provider: str):
        gen = self._run_generation
        try:
            from . import _get_engine, ping_pong
            self._engine = _get_engine(provider=provider)
            self._results = ping_pong(
                PINGPONG_WRITER, PINGPONG_REVIEWER, request,
                n=n, provider=provider,
            )
        except Exception as e:
            if gen == self._run_generation:
                self._error = str(e)
        finally:
            if gen == self._run_generation:
                self._done = True

    # ── Reactive ───────────────────────────────────────────────

    def _run_reactive(self):
        # 고정 시나리오 — 사용자 입력 불필요
        provider = self.provider_var.get()
        self._reset_state()
        self._draw_dag_reactive()

        thread = threading.Thread(
            target=self._execute_reactive,
            args=(provider,),
            daemon=True,
        )
        thread.start()
        self._poll_trace()

    def _execute_reactive(self, provider: str):
        gen = self._run_generation
        try:
            from . import _get_engine, reactive
            self._engine = _get_engine(provider=provider)
            self._results = reactive(
                REACTIVE_AGENT, REACTIVE_TICKS,
                tick_interval=REACTIVE_TICK_INTERVAL,
                threshold=REACTIVE_THRESHOLD,
                provider=provider,
            )
        except Exception as e:
            if gen == self._run_generation:
                self._error = str(e)
        finally:
            if gen == self._run_generation:
                self._done = True

    # ── Trace polling ─────────────────────────────────────────

    def _drain_events(self):
        if self._engine is None:
            return
        try:
            trace = self._engine.trace
            events = trace.events
        except Exception:
            return
        if trace is not self._last_trace:
            self._last_trace = trace
            self._trace_idx = 0
        while self._trace_idx < len(events):
            event = events[self._trace_idx]
            self._trace_idx += 1
            try:
                self._update_log(event)
                self._update_canvas(event)
            except Exception:
                pass

    def _poll_trace(self):
        # 이전 실행의 poll 취소
        if self._poll_after_id:
            self.root.after_cancel(self._poll_after_id)
            self._poll_after_id = None
        self._poll_generation += 1
        gen = self._poll_generation
        self._poll_tick(gen)

    def _poll_tick(self, gen: int):
        if gen != self._poll_generation:
            return
        self._drain_events()
        if not self._done:
            self._poll_after_id = self.root.after(200, self._poll_tick, gen)
        else:
            self._drain_events()
            self._poll_after_id = None
            self._on_complete()

    def _update_log(self, event):
        sym = EVENT_SYMBOLS.get(event.event, "--")
        ts = event.timestamp
        try:
            dt = datetime.fromisoformat(ts)
            ts_short = dt.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            ts_short = ts[:8] if ts else ""

        parts = [f"[{sym}] {ts_short}"]
        if event.agent:
            parts.append(event.agent)
        if event.detail:
            parts.append(event.detail)
        elif event.event == "master_think" and event.prompt_preview:
            parts.append(f"Master → {event.agent}")
        elif event.event == "agent_complete":
            elapsed = f"({event.elapsed_seconds:.1f}s)" if event.elapsed_seconds is not None else ""
            parts.append(f"완료 {elapsed}")
        elif event.event == "agent_error" and event.error:
            parts.append(f"오류: {event.error[:60]}")
        elif event.event == "pipeline_start":
            parts.append("파이프라인 시작")
        elif event.event == "pipeline_end":
            elapsed = f"{event.elapsed_seconds:.1f}s" if event.elapsed_seconds is not None else ""
            parts.append(f"파이프라인 종료 {elapsed}")

        line = "  ".join(parts) + "\n"

        tag_map = {
            "pipeline_start": "sym_start",
            "pipeline_end": "sym_end",
            "master_think": "sym_think",
            "agent_start": "sym_agent",
            "agent_complete": "sym_ok",
            "agent_error": "sym_err",
            "tick": "sym_tick",
            "trigger": "sym_trigger",
        }
        tag = tag_map.get(event.event, None)

        self.log_text.configure(state=tk.NORMAL)
        # 첫 이벤트 시 placeholder 제거
        if self.log_text.get("1.0", tk.END).strip() == LOG_PLACEHOLDER:
            self.log_text.delete("1.0", tk.END)
        if tag:
            self.log_text.insert(tk.END, line, tag)
        else:
            self.log_text.insert(tk.END, line)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ── Canvas update (dispatch) ──────────────────────────────

    def _update_canvas(self, event):
        if self._current_pattern == "loop":
            self._update_canvas_loop(event)
        elif self._current_pattern == "sequential":
            self._update_canvas_sequential(event)
        elif self._current_pattern == "parallel":
            self._update_canvas_parallel(event)
        elif self._current_pattern == "tool_call":
            self._update_canvas_tool_call(event)
        elif self._current_pattern == "ping_pong":
            self._update_canvas_ping_pong(event)
        elif self._current_pattern == "reactive":
            self._update_canvas_reactive(event)
        else:
            self._update_canvas_orchestration(event)

    def _update_canvas_orchestration(self, event):
        etype = event.event
        agent = event.agent

        if etype == "pipeline_start":
            self._set_node_color("Master", COLOR_MASTER_ACTIVE)
            self._start_pulse("Master")
            self._clear_live_edges()
            self._status_text = "Master 준비 중..."

        elif etype == "master_think":
            self._set_node_color("Master", COLOR_MASTER_ACTIVE)
            if agent:
                self._show_live_edge("Master", agent, color="#4A90D9")
                self._start_pulse(agent)
                self._set_node_color(agent, COLOR_AGENT_ACTIVE)
                self._status_text = f"Master → {agent} 지시 완료, 에이전트 실행 대기"

        elif etype == "agent_start":
            self._set_node_color("Master", COLOR_DONE)
            if agent:
                self._set_node_color(agent, COLOR_AGENT_ACTIVE)
                self._start_pulse(agent)
                self._status_text = f"{agent} 실행 중..."

        elif etype == "agent_complete":
            if agent:
                self._set_node_color(agent, COLOR_DONE)
                self._stop_pulse()
                self._show_live_edge(agent, "Master", color="#90EE90", dash=(6, 3))
                if event.elapsed_seconds is not None:
                    self._agent_elapsed[agent] = event.elapsed_seconds
                    self._set_node_subtext(agent, f"{event.elapsed_seconds:.1f}s")
                if event.output_preview:
                    self._agent_outputs[agent] = event.output_preview
                try:
                    idx = self._agent_names.index(agent)
                    if idx < len(self._agent_names) - 1:
                        next_agent = self._agent_names[idx + 1]
                        self._set_node_color("Master", COLOR_MASTER_ACTIVE)
                        self._start_pulse("Master")
                        self._status_text = f"Master가 {next_agent} 작업 지시 생성 중..."
                    else:
                        self._status_text = "마무리 중..."
                except ValueError:
                    pass

        elif etype == "agent_error":
            if agent:
                self._set_node_color(agent, COLOR_ERROR)
                self._stop_pulse()
                self._show_live_edge(agent, "Master", color=COLOR_ERROR, dash=(6, 3))
                self._status_text = f"{agent} 오류 발생"

        elif etype == "pipeline_end":
            self._set_node_color("Master", COLOR_DONE)
            self._stop_pulse()
            self._clear_live_edges()

    def _update_canvas_parallel(self, event):
        etype = event.event
        agent = event.agent

        if etype == "pipeline_start":
            self._set_node_color("Master", COLOR_MASTER_ACTIVE)
            self._start_pulse("Master")
            self._clear_live_edges()
            self._status_text = "Master 요구사항 생성 중..."

        elif etype == "master_think":
            self._set_node_color("Master", COLOR_MASTER_ACTIVE)
            if event.elapsed_seconds is not None:
                # 생성 완료
                self._set_node_color("Master", COLOR_DONE)
                self._stop_pulse()
                self._set_node_subtext("Master", f"{event.elapsed_seconds:.1f}s")
                if event.output_preview:
                    self._agent_outputs["Master"] = event.output_preview
                # Master → 모든 에이전트 라이브 엣지
                for name in self._agent_names:
                    pos_m = self._node_positions.get("Master")
                    pos_a = self._node_positions.get(name)
                    if pos_m and pos_a:
                        edge_id = self._draw_arrow(
                            self.canvas,
                            pos_m[0] + 60 + 4, pos_m[1],
                            pos_a[0] - 60 - 4, pos_a[1],
                            color="#4A90D9", width=3,
                        )
                        self._live_edge_ids.append(edge_id)
                self._status_text = "에이전트 병렬 실행 시작..."

        elif etype == "agent_start":
            if agent:
                self._set_node_color(agent, COLOR_AGENT_ACTIVE)
                self._start_pulse(agent)
                self._status_text = f"병렬 실행 중... ({agent} 시작)"

        elif etype == "agent_complete":
            if agent:
                self._set_node_color(agent, COLOR_DONE)
                self._stop_pulse(agent)
                if event.elapsed_seconds is not None:
                    self._agent_elapsed[agent] = event.elapsed_seconds
                    self._set_node_subtext(agent, f"{event.elapsed_seconds:.1f}s")
                if event.output_preview:
                    self._agent_outputs[agent] = event.output_preview
                self._status_text = f"{agent} 완료"

        elif etype == "agent_error":
            if agent:
                self._set_node_color(agent, COLOR_ERROR)
                self._status_text = f"{agent} 오류 발생"

        elif etype == "pipeline_end":
            self._stop_pulse()
            self._clear_live_edges()
            self._set_node_color("Master", COLOR_DONE)

    def _update_canvas_tool_call(self, event):
        etype = event.event
        agent = event.agent

        if etype == "pipeline_start":
            self._clear_live_edges()
            self._status_text = "Tool Calling 시작..."

        elif etype == "agent_start":
            if agent:
                self._set_node_color(agent, COLOR_AGENT_ACTIVE)
                self._start_pulse(agent)
                # worker → tool 라이브 엣지
                self._show_live_edge(agent, "random_dice", color="#FF9800")
                self._status_text = f"{agent} — 도구 사용 중..."

        elif etype == "agent_complete":
            if agent:
                self._set_node_color(agent, COLOR_DONE)
                self._stop_pulse()
                # tool → worker 반환 엣지
                self._show_live_edge("random_dice", agent,
                                     color="#90EE90", dash=(6, 3))
                if event.elapsed_seconds is not None:
                    self._agent_elapsed[agent] = event.elapsed_seconds
                    self._set_node_subtext(agent, f"{event.elapsed_seconds:.1f}s")
                if event.output_preview:
                    self._agent_outputs[agent] = event.output_preview
                self._status_text = f"{agent} 완료"

        elif etype == "agent_error":
            if agent:
                self._set_node_color(agent, COLOR_ERROR)
                self._stop_pulse()
                self._status_text = f"{agent} 오류 발생"

        elif etype == "pipeline_end":
            self._stop_pulse()
            self._clear_live_edges()

    def _update_canvas_sequential(self, event):
        etype = event.event
        agent = event.agent

        if etype == "pipeline_start":
            self._clear_live_edges()
            self._status_text = "Sequential 시작..."

        elif etype == "agent_start":
            if agent:
                self._set_node_color(agent, COLOR_AGENT_ACTIVE)
                self._start_pulse(agent)
                # 이전 에이전트 → 현재 에이전트 라이브 엣지
                try:
                    idx = self._agent_names.index(agent)
                    if idx > 0:
                        prev = self._agent_names[idx - 1]
                        self._show_live_edge(prev, agent, color="#4A90D9")
                except ValueError:
                    pass
                self._status_text = f"{agent} 실행 중..."

        elif etype == "agent_complete":
            if agent:
                self._set_node_color(agent, COLOR_DONE)
                self._stop_pulse()
                self._clear_live_edges()
                if event.elapsed_seconds is not None:
                    self._agent_elapsed[agent] = event.elapsed_seconds
                    self._set_node_subtext(agent, f"{event.elapsed_seconds:.1f}s")
                if event.output_preview:
                    self._agent_outputs[agent] = event.output_preview
                self._status_text = f"{agent} 완료"

        elif etype == "agent_error":
            if agent:
                self._set_node_color(agent, COLOR_ERROR)
                self._stop_pulse()
                self._status_text = f"{agent} 오류 발생"

        elif etype == "pipeline_end":
            self._stop_pulse()
            self._clear_live_edges()

    def _update_canvas_loop(self, event):
        etype = event.event
        agent = event.agent

        if etype == "pipeline_start":
            if self._agent_names:
                self._set_node_color(self._agent_names[0], COLOR_IDLE)
            self._clear_live_edges()
            self._status_text = "Loop 시작..."

        elif etype == "agent_start":
            if agent:
                self._set_node_color(agent, COLOR_AGENT_ACTIVE)
                self._start_pulse(agent)
                self._clear_live_edges()
                self._show_active_loop_arrow(agent, color="#4A90D9")
                if event.detail:
                    self._set_node_subtext(agent, event.detail)
                    self._status_text = f"{agent} — {event.detail}"
                else:
                    self._status_text = f"{agent} 실행 중..."

        elif etype == "agent_complete":
            if agent:
                self._stop_pulse()
                if event.elapsed_seconds is not None:
                    self._agent_elapsed[agent] = event.elapsed_seconds
                if event.output_preview:
                    self._loop_outputs.append(event.output_preview)
                if event.detail:
                    self._set_node_subtext(agent, f"{event.detail} \u2713")
                self._set_node_color(agent, COLOR_DONE)
                self._clear_live_edges()
                self._show_active_loop_arrow(agent, color="#90EE90")
                self._status_text = f"{agent} — {event.detail or ''} 완료"

        elif etype == "agent_error":
            if agent:
                self._set_node_color(agent, COLOR_ERROR)
                self._stop_pulse()
                self._status_text = f"{agent} 오류 발생"

        elif etype == "pipeline_end":
            if self._agent_names:
                self._set_node_color(self._agent_names[0], COLOR_DONE)
            self._stop_pulse()
            self._clear_live_edges()

    def _update_canvas_ping_pong(self, event):
        etype = event.event
        agent = event.agent

        if etype == "pipeline_start":
            self._set_node_color(PINGPONG_WRITER, COLOR_IDLE)
            self._set_node_color(PINGPONG_REVIEWER, COLOR_IDLE)
            self._clear_live_edges()
            self._status_text = "Ping-Pong 시작..."

        elif etype == "agent_start":
            if agent:
                self._set_node_color(agent, COLOR_AGENT_ACTIVE)
                self._start_pulse(agent)
                # 라이브 엣지: 현재 턴 방향
                if agent == PINGPONG_WRITER:
                    # reviewer → writer (피드백 기반 개선) 또는 첫 턴
                    other = PINGPONG_REVIEWER
                    if self._node_colors.get(other) == COLOR_DONE:
                        self._show_live_edge(other, agent, color="#4A90D9")
                else:
                    # writer → reviewer (결과물 전달)
                    self._show_live_edge(PINGPONG_WRITER, agent, color="#4A90D9")
                if event.detail:
                    self._set_node_subtext(agent, event.detail)
                    self._status_text = f"{agent} — {event.detail}"
                else:
                    self._status_text = f"{agent} 실행 중..."

        elif etype == "agent_complete":
            if agent:
                self._set_node_color(agent, COLOR_DONE)
                self._stop_pulse()
                self._clear_live_edges()
                if event.elapsed_seconds is not None:
                    self._agent_elapsed[agent] = event.elapsed_seconds
                if event.output_preview:
                    self._agent_outputs[agent] = event.output_preview
                if event.detail:
                    self._set_node_subtext(agent, event.detail)
                self._status_text = f"{agent} — {event.detail or '완료'}"

        elif etype == "agent_error":
            if agent:
                self._set_node_color(agent, COLOR_ERROR)
                self._stop_pulse()
                self._status_text = f"{agent} 오류 발생"

        elif etype == "pipeline_end":
            self._set_node_color(PINGPONG_WRITER, COLOR_DONE)
            self._set_node_color(PINGPONG_REVIEWER, COLOR_DONE)
            self._stop_pulse()
            self._clear_live_edges()

    def _update_canvas_reactive(self, event):
        etype = event.event
        agent = event.agent

        if etype == "pipeline_start":
            self._clear_live_edges()
            self._set_node_color("Generator", COLOR_IDLE)
            self._set_node_color("Observer", "#FFF3E0")
            self._set_node_color(REACTIVE_AGENT, COLOR_IDLE)
            self._status_text = "Reactive — 데이터 수집 대기..."

        elif etype == "tick":
            self._set_node_color("Generator", COLOR_AGENT_ACTIVE)
            self._start_pulse("Generator")
            # Generator → Observer 라이브 엣지
            self._clear_live_edges()
            self._show_live_edge("Generator", "Observer", color="#4A90D9")
            # Observer subtext에 현재 큐 크기 표시
            if event.detail:
                # detail = "tick 5/20" → 숫자 추출
                try:
                    tick_num = event.detail.split()[1].split("/")[0]
                    self._set_node_subtext("Observer", f"Queue: {tick_num}/{REACTIVE_THRESHOLD}")
                except (IndexError, ValueError):
                    pass
            self._status_text = f"Generator — {event.detail or 'tick'}"

        elif etype == "trigger":
            self._set_node_color("Generator", COLOR_DONE)
            self._stop_pulse()
            self._set_node_color("Observer", "#FF9800")
            self._clear_live_edges()
            self._show_live_edge("Observer", REACTIVE_AGENT, color="#FF9800")
            self._set_node_subtext("Observer", f"Queue: {REACTIVE_THRESHOLD}/{REACTIVE_THRESHOLD} !")
            self._status_text = "Observer — threshold 도달! 에이전트 트리거"

        elif etype == "agent_start":
            if agent == REACTIVE_AGENT:
                self._set_node_color(REACTIVE_AGENT, COLOR_AGENT_ACTIVE)
                self._start_pulse(REACTIVE_AGENT)
                self._status_text = f"{REACTIVE_AGENT} — 이상 탐지 분석 중..."

        elif etype == "agent_complete":
            if agent == REACTIVE_AGENT:
                self._set_node_color(REACTIVE_AGENT, COLOR_DONE)
                self._stop_pulse()
                self._clear_live_edges()
                if event.elapsed_seconds is not None:
                    self._agent_elapsed[agent] = event.elapsed_seconds
                    self._set_node_subtext(agent, f"{event.elapsed_seconds:.1f}s")
                if event.output_preview:
                    self._agent_outputs[agent] = event.output_preview
                self._status_text = f"{REACTIVE_AGENT} — 분석 완료"

        elif etype == "agent_error":
            if agent:
                self._set_node_color(agent, COLOR_ERROR)
                self._stop_pulse()
                self._status_text = f"{agent} 오류 발생"

        elif etype == "pipeline_end":
            self._stop_pulse()
            self._clear_live_edges()
            self._set_node_color("Generator", COLOR_DONE)
            self._set_node_color("Observer", COLOR_DONE)
            self._set_node_color(REACTIVE_AGENT, COLOR_DONE)

    # ── Completion ────────────────────────────────────────────

    def _on_complete(self):
        self._running = False
        self._engine = None
        self._stop_pulse()
        self._stop_elapsed_timer()
        # 설정 복원 + 버튼을 실행으로 변경
        self._set_config_enabled(True)
        # Tool Calling / Reactive: 고정 프롬프트 모드에서는 Request 비활성 유지
        if self._current_pattern in ("tool_call", "reactive"):
            self.request_text.configure(state=tk.DISABLED)
        self.run_btn.configure(
            text="\u25b6  실행", command=self._run_pipeline,
            bg=COLOR_ACCENT, fg=COLOR_ACCENT if _IS_MACOS else "white",
            activebackground="#3A7BC8",
            state=tk.NORMAL,
        )
        self._set_status("중단됨" if self._interrupted else "완료")

        if self._results and self._agent_names:
            if self._current_pattern in ("orchestration", "sequential", "parallel", "tool_call"):
                for i, name in enumerate(self._agent_names):
                    if i < len(self._results):
                        self._agent_outputs[name] = self._results[i].text
            elif self._current_pattern == "loop":
                self._loop_outputs = [r.text for r in self._results]

        if self._error:
            messagebox.showerror("실행 오류", self._error)
            self._error = None
            if self._current_pattern == "orchestration":
                self._set_node_color("Master", COLOR_ERROR)
            elif self._agent_names:
                self._set_node_color(self._agent_names[0], COLOR_ERROR)


def launch():
    """GUI 시작 진입점."""
    root = tk.Tk()
    PipelineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch()
