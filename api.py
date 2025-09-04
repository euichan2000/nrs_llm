# api.py (refactored to receive and log env pipe messages)
class API:
    def __init__(self, pipe, logger=None):
        self.pipe = pipe
        self.command = ""
        self.completed = False
        self.log = logger.info if logger and hasattr(logger, "info") else print

    def _send_and_log(self, message):
        self.pipe.send(message)
        result = self.pipe.recv()
        if isinstance(result, str) and result.startswith("[env]"):
            self.log(result)
        return result

    def get_fingertip_position(self):
        self.log("[API] Requesting fingertip position...")
        self.pipe.send({"action": "get_point"})
        result = self.pipe.recv()
        self.log(f"[API] Received: {result}")

        point = None
        if isinstance(result, str):
            coords = {}
            for line in result.splitlines():
                if ':' in line:
                    key, val = line.split(':', 1)
                    key, val = key.strip(), val.strip()
                    if key in ['x', 'y', 'z']:
                        try:
                            coords[key] = float(val)
                        except:
                            pass
            if all(k in coords for k in ['x', 'y', 'z']):
                point = [coords['x'], coords['y'], coords['z']]
        elif isinstance(result, dict) and all(k in result for k in ['x', 'y', 'z']):
            point = [result['x'], result['y'], result['z']]
        return point if point else result

    def scan(self):
        self.log("[API] Scanning object...")
        return self._send_and_log({"action": "scan"})

    def register(self):
        self.log("[API] Registering point clouds...")
        return self._send_and_log({"action": "register"})

    def reconstruct(self):
        self.log("[API] Reconstructing mesh...")
        return self._send_and_log({"action": "reconstruct"})

    def plan_tool_path(self, pattern, pressure, speed):
        self.log("[API] Planning tool path...")
        return self._send_and_log({
            "action": "plan",
            "pattern": pattern,
            "pressure": pressure,
            "speed": speed
        })

    def interpolate(self):
        self.log("[API] Interpolating path...")
        return self._send_and_log({"action": "interpolate"})

    def save_waypoints(self):
        self.log("[API] Saving waypoints...")
        return self._send_and_log({"action": "save"})

    def generate_polishing_path(self, target_point, pattern, pressure, speed):
        self.log(f"[API] Generating path: point={target_point}, pattern={pattern}, pressure={pressure}, speed={speed}")
        result = self._send_and_log({
            "action": "generate_path",
            "target": target_point,
            "pattern": pattern,
            "pressure": pressure,
            "speed": speed
        })
        if isinstance(result, str) and result.startswith("[env] Path generation failed"):
            raise RuntimeError(result)
        return result

    def execute_polishing_path(self):
        self.log("[API] Executing polishing path...")
        result = self._send_and_log({"action": "execute_path"})
        if isinstance(result, str) and result.startswith("[env] Execution failed"):
            raise RuntimeError(result)
        return result

    def task_completed(self):
        self.log("[API] Task completed.")
        self.completed = True
        return True

    def task_failed(self):
        self.log("[API] Task failed.")
        self.completed = False
        return False

    def check_task_success(self):
        return self.completed
