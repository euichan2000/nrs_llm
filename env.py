
# =========================
# env.py  (list-only IPC)
# =========================
# -*- coding: utf-8 -*-
"""
RTDE 전용 환경 프로세스 (list-only IPC).

수신 패킷(상위→env):
  ["log", msg, ts]
  ["ping", ts]
  ["set_last_command", text, ts]
  ["move_linear", [dx,dy,dz], speed, frame, ts]
  ["move_cartesian", [x,y,z], orientation_or_none, speed, frame, ts]
  ["move_joints", [q1..q6], speed, ts]

송신 패킷(env→상위):
  ["status", state, msg, [x,y,z], [qx,qy,qz,qw], joints(6), ts]
  ["debug", msg, ts]
  ["pong", backend, connected, ts]
"""

import os
import time
import math
import traceback
from typing import List

# ===================== 공통 유틸 =====================

def now_ts() -> float:
    return time.time()

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def axis_angle_to_R(rx, ry, rz):
    theta = math.sqrt(rx*rx + ry*ry + rz*rz)
    if theta < 1e-12:
        return [[1,0,0],[0,1,0],[0,0,1]]
    kx, ky, kz = rx/theta, ry/theta, rz/theta
    c = math.cos(theta)
    s = math.sin(theta)
    v = 1.0 - c
    return [
        [kx*kx*v + c,     kx*ky*v - kz*s, kx*kz*v + ky*s],
        [ky*kx*v + kz*s,  ky*ky*v + c,    ky*kz*v - kx*s],
        [kz*kx*v - ky*s,  kz*ky*v + kx*s, kz*kz*v + c   ]
    ]

def mat_vec3(M, v):
    return [
        M[0][0]*v[0] + M[0][1]*v[1] + M[0][2]*v[2],
        M[1][0]*v[0] + M[1][1]*v[1] + M[1][2]*v[2],
        M[2][0]*v[0] + M[2][1]*v[1] + M[2][2]*v[2],
    ]

def quat_normalize(q):
    x,y,z,w = q
    n = math.sqrt(x*x+y*y+z*z+w*w)
    if n < 1e-12:
        return [0.0,0.0,0.0,1.0]
    return [x/n, y/n, z/n, w/n]

def quat_to_axis_angle(q):
    x,y,z,w = quat_normalize(q)
    w = clamp(w, -1.0, 1.0)
    angle = 2.0 * math.acos(w)
    s = math.sqrt(1 - w*w)
    if s < 1e-8:
        return [angle, 0.0, 0.0] if angle != 0.0 else [0.0,0.0,0.0]
    kx, ky, kz = x/s, y/s, z/s
    return [kx*angle, ky*angle, kz*angle]

def axis_angle_to_quat(rx, ry, rz):
    theta = math.sqrt(rx*rx + ry*ry + rz*rz)
    if theta < 1e-12:
        return [0.0,0.0,0.0,1.0]
    ax, ay, az = rx/theta, ry/theta, rz/theta
    s = math.sin(theta/2.0)
    c = math.cos(theta/2.0)
    return [ax*s, ay*s, az*s, c]

# ===================== 백엔드 인터페이스 =====================

class BaseBackend:
    name = "base"

    def __init__(self, send_fn):
        """send_fn: list 패킷 송신 함수(list -> None)"""
        self._send = send_fn
        self._last_cmd_text = ""
        self._moving = False

    # 필수 메서드
    def connect(self): ...
    def shutdown(self): ...
    def is_connected(self) -> bool: return False

    def get_tcp_pose(self) -> List[float]:
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # [x,y,z,rx,ry,rz]

    def get_joints(self) -> List[float]:
        return [0.0]*6

    def moveL(self, target_pose: List[float], speed: float, accel: float):
        raise NotImplementedError

    def moveJ(self, q: List[float], speed: float, accel: float):
        raise NotImplementedError

    # 헬퍼: 상태 송신 (list)
    def _status(self, state: str, msg: str = ""):
        tcp = self.get_tcp_pose()
        x,y,z, rx,ry,rz = tcp
        pose_xyz = [x,y,z]
        pose_quat = axis_angle_to_quat(rx,ry,rz)
        joints = self.get_joints()
        self._send(["status", state, msg, pose_xyz, pose_quat, joints, now_ts()])

    def _debug(self, msg: str):
        self._send(["debug", str(msg), now_ts()])

    # 고수준 동작
    def move_linear(self, dxyz: List[float], speed: float, frame: str):
        if len(dxyz) != 3:
            raise ValueError("dxyz must have length 3")
        speed = clamp(float(speed), 0.01, 0.25)
        self._status("moving", f"move_linear {dxyz} @ {speed} m/s frame={frame}")
        self._moving = True
        try:
            x, y, z, rx, ry, rz = self.get_tcp_pose()
            if frame == "tool":
                R = axis_angle_to_R(rx, ry, rz)
                d_base = mat_vec3(R, dxyz)
                tx, ty, tz = x + d_base[0], y + d_base[1], z + d_base[2]
            else:
                tx, ty, tz = x + dxyz[0], y + dxyz[1], z + dxyz[2]
            target = [tx, ty, tz, rx, ry, rz]
            accel = float(os.getenv("UR_ACCEL", "0.2"))
            self._debug(f"[{self.name}] moveL target={target}, v={speed}, a={accel}")
            self.moveL(target, speed, accel)
            self._status("idle", "done")
        except Exception as e:
            self._status("error", f"move_linear failed: {e}")
            self._debug(traceback.format_exc())
        finally:
            self._moving = False

    def move_cartesian(self, pos_xyz: List[float], orientation_quat_or_none, speed: float, frame: str):
        speed = clamp(float(speed), 0.01, 0.25)
        self._status("moving", f"move_cartesian {pos_xyz} @ {speed} m/s frame={frame}")
        self._moving = True
        try:
            curx, cury, curz, rx, ry, rz = self.get_tcp_pose()
            tx, ty, tz = float(pos_xyz[0]), float(pos_xyz[1]), float(pos_xyz[2])
            if orientation_quat_or_none is not None:
                q = list(orientation_quat_or_none)
                if len(q) != 4:
                    raise ValueError("orientation must be [qx,qy,qz,qw] or None")
                rx, ry, rz = quat_to_axis_angle(q)
            pose = [tx, ty, tz, rx, ry, rz]
            accel = float(os.getenv("UR_ACCEL", "0.2"))
            self._debug(f"[{self.name}] moveL target={pose}, v={speed}, a={accel}")
            self.moveL(pose, speed, accel)
            self._status("idle", "done")
        except Exception as e:
            self._status("error", f"move_cartesian failed: {e}")
            self._debug(traceback.format_exc())
        finally:
            self._moving = False

    def move_joints(self, q: List[float], speed: float):
        if not isinstance(q, (list, tuple)) or len(q) != 6:
            raise ValueError("q must be list/tuple of length 6 (rad)")
        js = clamp(float(speed), 0.05, 1.5)
        self._status("moving", f"move_joints {list(q)} @ {js} rad/s")
        self._moving = True
        try:
            accel = float(os.getenv("UR_JOINT_ACCEL", "1.0"))
            self._debug(f"[{self.name}] moveJ q={list(q)}, v={js}, a={accel}")
            self.moveJ(list(q), js, accel)
            self._status("idle", "done")
        except Exception as e:
            self._status("error", f"move_joints failed: {e}")
            self._debug(traceback.format_exc())
        finally:
            self._moving = False

# ===================== RTDE 백엔드 =====================

class RTDEBackend(BaseBackend):
    name = "rtde"

    def __init__(self, send_fn):
        super().__init__(send_fn)
        self.host = os.getenv("UR_HOST", "192.168.0.47")
        self.speed_default = float(os.getenv("UR_SPEED", "0.05"))
        self.acc_default = float(os.getenv("UR_ACCEL", "0.2"))
        self.joint_acc_default = float(os.getenv("UR_JOINT_ACCEL", "1.0"))
        self.rtde_c = None
        self.rtde_r = None

    def is_connected(self) -> bool:
        return (self.rtde_c is not None) and (self.rtde_r is not None)

    def connect(self):
        try:
            import rtde_control, rtde_receive
        except Exception as e:
            raise RuntimeError(f"ur_rtde 불러오기 실패: {e}")
        try:
            self.rtde_c = rtde_control.RTDEControlInterface(self.host)
            self.rtde_r = rtde_receive.RTDEReceiveInterface(self.host)
            self._status("idle", f"RTDE connected to {self.host}")
        except Exception as e:
            self.rtde_c = None
            self.rtde_r = None
            raise RuntimeError(f"RTDE 접속 실패: {e}")

    def shutdown(self):
        try:
            if self.rtde_c:
                self.rtde_c.stopScript()
                self.rtde_c.disconnect()
            if self.rtde_r:
                self.rtde_r.disconnect()
        except Exception:
            pass
        finally:
            self.rtde_c, self.rtde_r = None, None
            self._debug("[rtde] shutdown complete")

    def get_tcp_pose(self) -> List[float]:
        if not self.rtde_r:
            return super().get_tcp_pose()
        pose = self.rtde_r.getActualTCPPose()  # [x,y,z,rx,ry,rz]
        if not pose or len(pose) != 6:
            return super().get_tcp_pose()
        return list(pose)

    def get_joints(self) -> List[float]:
        if not self.rtde_r:
            return super().get_joints()
        q = self.rtde_r.getActualQ()
        if not q or len(q) != 6:
            return super().get_joints()
        return list(q)

    def moveL(self, target_pose: List[float], speed: float, accel: float):
        if not self.rtde_c:
            raise RuntimeError("RTDE control not connected")
        v = clamp(speed, 0.01, 0.25)
        a = clamp(accel, 0.05, 1.5)
        ok = self.rtde_c.moveL(target_pose, v, a, asynchronous=False)
        if not ok:
            raise RuntimeError("rtde_control.moveL returned False")

    def moveJ(self, q: List[float], speed: float, accel: float):
        if not self.rtde_c:
            raise RuntimeError("RTDE control not connected")
        v = clamp(speed, 0.05, 1.5)
        a = clamp(accel, 0.2, 5.0)
        ok = self.rtde_c.moveJ(q, v, a, asynchronous=False)
        if not ok:
            raise RuntimeError("rtde_control.moveJ returned False")

# ===================== 런타임 루프 =====================

def run_environment(child_conn):
    """
    main.py에서 multiprocessing.Process(target=run_environment, args=(child_conn,))로 실행.
    RTDE 연결 실패 시 error 상태 송신 후 즉시 종료한다.
    """
    def send(msg_list):
        try:
            child_conn.send(msg_list)
        except Exception:
            pass

    # RTDE 전용 백엔드 인스턴스화 및 연결 시도
    try:
        backend = RTDEBackend(send)
        backend.connect()
        if not backend.is_connected():
            raise RuntimeError("RTDE not connected (unknown reason)")
    except Exception as e:
        send(["status","error",f"RTDE 연결 실패: {e}",[0,0,0],[0,0,0,1],[0]*6, now_ts()])
        send(["debug","[env] RTDE required; terminating env process", now_ts()])
        return

    send(["debug", f"[env] using backend: {backend.name}", now_ts()])

    last_command_text = ""

    try:
        while True:
            try:
                pkt = child_conn.recv()  # 블로킹 수신
            except EOFError:
                break
            except Exception:
                send(["status","error","pipe recv failed", [0,0,0],[0,0,0,1],[0]*6, now_ts()])
                break

            if not isinstance(pkt, (list, tuple)) or not pkt:
                send(["debug", f"[env] ignore invalid pkt: {pkt}", now_ts()])
                continue

            tag = pkt[0]
            try:
                if tag == "log":
                    # ["log", msg, ts]
                    msg = str(pkt[1]) if len(pkt) > 1 else ""
                    send(["debug", f"[log] {msg}", now_ts()])

                elif tag == "ping":
                    send(["pong", backend.name, backend.is_connected(), now_ts()])

                elif tag == "set_last_command":
                    # ["set_last_command", text, ts]
                    last_command_text = str(pkt[1]) if len(pkt) > 1 else ""
                    backend._last_cmd_text = last_command_text
                    send(["debug", f"[env] last_command='{last_command_text}'", now_ts()])

                elif tag == "move_linear":
                    # ["move_linear", [dx,dy,dz], speed, frame, ts]
                    dxyz = pkt[1] if len(pkt) > 1 else [0,0,0]
                    speed = float(pkt[2]) if len(pkt) > 2 else float(os.getenv("UR_SPEED","0.05"))
                    frame = pkt[3] if len(pkt) > 3 else "tool"
                    backend.move_linear(dxyz, speed, frame)

                elif tag == "move_cartesian":
                    # ["move_cartesian", [x,y,z], orientation_or_none, speed, frame, ts]
                    pos = pkt[1] if len(pkt) > 1 else [0,0,0]
                    orient = pkt[2] if len(pkt) > 2 else None
                    speed = float(pkt[3]) if len(pkt) > 3 else float(os.getenv("UR_SPEED","0.05"))
                    frame = pkt[4] if len(pkt) > 4 else "tool"
                    backend.move_cartesian(pos, orient, speed, frame)

                elif tag == "move_joints":
                    # ["move_joints", [q1..q6], speed, ts]
                    q = pkt[1] if len(pkt) > 1 else [0,0,0,0,0,0]
                    speed = float(pkt[2]) if len(pkt) > 2 else float(os.getenv("UR_JOINT_SPEED","0.3"))
                    backend.move_joints(q, speed)

                else:
                    send(["status","error",f"unknown op '{tag}'", [0,0,0],[0,0,0,1],[0]*6, now_ts()])

            except Exception as e:
                send(["status","error",f"{tag} failed: {e}",[0,0,0],[0,0,0,1],[0]*6, now_ts()])
                send(["debug", traceback.format_exc(), now_ts()])

    finally:
        try:
            backend.shutdown()
        except Exception:
            pass
        send(["debug","[env] terminated", now_ts()])
