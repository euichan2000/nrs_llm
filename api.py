# =========================
# api.py  (list-only IPC)
# =========================
# -*- coding: utf-8 -*-
import time
import math
from typing import Optional, List

SAFE_MAX_STEP_M = 0.20
SAFE_MIN_STEP_M = 0.005
SAFE_DEFAULT_SPEED = 0.05  # m/s
SAFE_MIN_SPEED = 0.01
SAFE_MAX_SPEED = 0.25

class API:
    """
    상위 LLM 코드가 호출하는 안전한 로봇 제어 API 래퍼 (list-only IPC).
    - 파이프(pipe)로 env 프로세스에 '리스트' 패킷을 전송
    - 수신은 main.py 쪽에서 처리하며, 본 API는 필요 시 ingest_env_message 로 캐시만 갱신

    패킷 규격 (모두 list):
      ➤ 발신(상위→env)
        ["log", msg:str, ts:float]
        ["ping", ts:float]
        ["set_last_command", text:str, ts:float]
        ["move_linear", [dx,dy,dz], speed:float, frame:"tool"|"base", ts:float]
        ["move_cartesian", [x,y,z], orientation_or_none:[qx,qy,qz,qw]|None, speed:float, frame:"tool"|"base", ts:float]
        ["move_joints", [q1..q6], speed:float, ts:float]

      ➤ 수신(env→상위)
        ["status", state:"idle"|"moving"|"error", msg:str, [x,y,z], [qx,qy,qz,qw], joints:[6], ts:float]
        ["debug", msg:str, ts:float]
        ["pong", backend:str, connected:bool, ts:float]
    """

    def __init__(self, pipe=None, logger=None):
        self.pipe = pipe
        self.logger = logger
        self.completed: bool = False
        self._task_success: Optional[bool] = None

        self._busy: bool = False
        self._ready_at: float = 0.0  # 동작이 끝났다고 추정되는 시각

        self.last_command: str = ""
        # 포즈 캐시: list 통일 [x,y,z]
        self._tool_pos_cache: List[float] = [0.0, 0.0, 0.0]
        self._connected: bool = False
        self._backend: str = ""
        self._last_status = None

    # ---------- 유틸 ----------
    def _log(self, msg: str):
        if self.logger:
            self.logger.info(msg)
        else:
            print(msg)

    def print(self, msg: str):
        """LLM 출력 통일. env로도 포워딩."""
        self._log(f"[API] {msg}")
        self._send(["log", str(msg), time.time()])

    def sleep(self, seconds: float):
        time.sleep(max(0.0, float(seconds)))

    def is_busy(self) -> bool:
        # 내부 추정으로 busy 판단
        now = time.time()
        if self._busy and now >= self._ready_at:
            self._busy = False
        return self._busy

    # ---------- 성공 플래그 ----------
    def task_success(self, flag: bool = True):
        self._task_success = bool(flag)
        self.completed = bool(flag)

    def set_task_success(self, flag: bool):
        self._task_success = bool(flag)
        self.completed = self.completed or bool(flag)

    def set_completed(self, flag: bool):
        self.completed = bool(flag)

    def check_task_success(self) -> bool:
        """최근 작업 성공 여부."""
        return bool(getattr(self, "_task_success", False) or getattr(self, "completed", False))

    # ---------- 포즈 ----------
    def get_pose(self, frame: str = "tool") -> List[float]:
        """
        동기 응답이 없으므로 즉시 정확 포즈는 불가. 최근 캐시 반환.
        통일: list [x,y,z]
        """
        if frame not in ("tool", "base"):
            raise ValueError("frame must be 'tool' or 'base'")
        return list(self._tool_pos_cache)

    # ---------- 이동 명령 ----------
    def move_linear(self, dxyz: List[float], speed: Optional[float] = None, frame: str = "tool"):
        if not isinstance(dxyz, (list, tuple)) or len(dxyz) != 3:
            raise ValueError("dxyz must be a list/tuple of length 3")

        dx, dy, dz = map(float, dxyz)
        step_vec_norm = math.sqrt(dx*dx + dy*dy + dz*dz)
        step = max(SAFE_MIN_STEP_M, min(step_vec_norm, SAFE_MAX_STEP_M))
        if step_vec_norm > 0:
            scale = step / step_vec_norm
            dx, dy, dz = dx * scale, dy * scale, dz * scale

        spd = SAFE_DEFAULT_SPEED if speed is None else float(speed)
        spd = max(SAFE_MIN_SPEED, min(spd, SAFE_MAX_SPEED))

        if frame not in ("tool", "base"):
            raise ValueError("frame must be 'tool' or 'base'")

        pkt = ["move_linear", [dx, dy, dz], spd, frame, time.time()]
        self._send(pkt)

        duration = step / spd if spd > 0 else 0.0
        self._mark_busy_for(duration)

        # 캐시 업데이트(대략)
        self._tool_pos_cache[0] += dx
        self._tool_pos_cache[1] += dy
        self._tool_pos_cache[2] += dz

    def move_cartesian(self, pos: List[float], orientation: Optional[List[float]] = None,
                       speed: Optional[float] = None, frame: str = "tool"):
        """
        절대 포지션/자세 이동 (list-only)
          pos: [x,y,z]
          orientation: [qx,qy,qz,qw] 또는 None (None이면 현재 유지)
        """
        if not isinstance(pos, (list, tuple)) or len(pos) != 3:
            raise ValueError("pos must be [x,y,z]")
        if orientation is not None:
            if not isinstance(orientation, (list, tuple)) or len(orientation) != 4:
                raise ValueError("orientation must be [qx,qy,qz,qw] or None")
            orientation = [float(v) for v in orientation]

        x, y, z = map(float, pos)
        spd = SAFE_DEFAULT_SPEED if speed is None else float(speed)
        spd = max(SAFE_MIN_SPEED, min(spd, SAFE_MAX_SPEED))

        if frame not in ("tool", "base"):
            raise ValueError("frame must be 'tool' or 'base'")

        pkt = ["move_cartesian", [x, y, z], orientation, spd, frame, time.time()]
        self._send(pkt)

        dx = x - self._tool_pos_cache[0]
        dy = y - self._tool_pos_cache[1]
        dz = z - self._tool_pos_cache[2]
        step = math.sqrt(dx*dx + dy*dy + dz*dz)
        duration = step / spd if spd > 0 else 0.0
        self._mark_busy_for(duration)

        self._tool_pos_cache = [x, y, z]

    def move_joints(self, q: List[float], speed: float = 0.3):
        if not isinstance(q, (list, tuple)) or len(q) != 6:
            raise ValueError("q must be list/tuple of length 6 (rad)")
        pkt = ["move_joints", [float(v) for v in q], float(speed), time.time()]
        self._send(pkt)

    # ---------- 완료 대기 ----------
    def wait_until_idle(self, timeout_s: float = 5.0) -> bool:
        deadline = time.time() + max(0.0, float(timeout_s))
        while time.time() < deadline:
            if not self.is_busy():
                return True
            time.sleep(0.05)
        return not self.is_busy()

    # ---------- 내부 도움 ----------
    def _mark_busy_for(self, seconds: float):
        seconds = max(0.0, float(seconds))
        guard = min(0.5, 0.1 + 0.1 * seconds)
        self._busy = True
        self._ready_at = time.time() + seconds + guard

    def _send(self, pkt: List):
        """env.py가 이해할 수 있는 '리스트' 패킷을 전송."""
        if self.pipe is not None:
            try:
                self.pipe.send(pkt)
            except Exception as e:
                self._log(f"[API] pipe send failed: {e}")

    # ---------- env 수신 반영 ----------
    def ingest_env_message(self, msg):
        """env.py에서 올라오는 메시지를 받아 내부 상태를 갱신 (list-only)."""
        try:
            if not isinstance(msg, (list, tuple)):
                return
            if not msg:
                return
            tag = msg[0]
            if tag == "status" and len(msg) >= 7:
                # ["status", state, msg, [x,y,z], [qx,qy,qz,qw], joints, ts]
                state = msg[1]
                pos = msg[3] if isinstance(msg[3], (list, tuple)) and len(msg[3]) == 3 else None
                if pos:
                    self._tool_pos_cache = [float(pos[0]), float(pos[1]), float(pos[2])]
                self._connected = state in ("idle", "moving")
                self._last_status = msg
            elif tag == "debug" and len(msg) >= 3:
                m = str(msg[1])
                if "using backend:" in m:
                    self._backend = m.split("using backend:")[-1].strip()
            elif tag == "pong" and len(msg) >= 4:
                self._backend = str(msg[1])
                self._connected = bool(msg[2])
        except Exception:
            pass

    def is_connected(self) -> bool:
        return bool(getattr(self, "_connected", False))

    def backend_name(self) -> str:
        return getattr(self, "_backend", "")

    def request_status(self):
        """env에 ping을 보내 연결/백엔드 정보를 요청."""
        self._send(["ping", time.time()])

    # ---------- 상위 루프와의 연동 ----------
    @property
    def command(self) -> str:
        return self.last_command

    @command.setter
    def command(self, cmd: str):
        self.last_command = str(cmd or "")
        self._send(["set_last_command", self.last_command, time.time()])

