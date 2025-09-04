
# env.py
import rospy
import subprocess
from std_srvs.srv import Empty

def run_environment(pipe):
    rospy.init_node("llm_env_listener", anonymous=True)
    rospy.loginfo("[ENV] Started LLM environment listener.")

    while not rospy.is_shutdown():
        if pipe.poll():
            req = pipe.recv()
            action = req.get("action", "")

            try:
                if action == "get_point":
                    output = subprocess.check_output(["rostopic", "echo", "-n", "1", "/hand_pointed_position"])
                    pipe.send(output.decode('utf-8', errors='ignore'))

                elif action == "scan":
                    rospy.wait_for_service('/scan', timeout=5.0)
                    rospy.ServiceProxy('/scan', Empty)()
                    pipe.send("[env] Scan completed.")

                elif action == "register":
                    rospy.wait_for_service('/registration', timeout=5.0)
                    rospy.ServiceProxy('/registration', Empty)()
                    pipe.send("[env] Registration completed.")

                elif action == "reconstruct":
                    rospy.wait_for_service('/reconstruction', timeout=5.0)
                    rospy.ServiceProxy('/reconstruction', Empty)()
                    pipe.send("[env] Reconstruction completed.")

                elif action == "plan":
                    if req.get("pattern"): rospy.set_param('/polishing_pattern', req["pattern"])
                    if req.get("pressure"): rospy.set_param('/polishing_pressure', req["pressure"])
                    if req.get("speed"): rospy.set_param('/polishing_speed', req["speed"])
                    rospy.wait_for_service('/tool_path_planning', timeout=5.0)
                    rospy.ServiceProxy('/tool_path_planning', Empty)()
                    pipe.send("[env] Tool path planned.")

                elif action == "interpolate":
                    rospy.wait_for_service('/interpolate', timeout=5.0)
                    rospy.ServiceProxy('/interpolate', Empty)()
                    pipe.send("[env] Interpolation completed.")

                elif action == "save":
                    rospy.wait_for_service('/waypoints_save', timeout=5.0)
                    rospy.ServiceProxy('/waypoints_save', Empty)()
                    pipe.send("[env] Waypoints saved.")

                elif action == "generate_path":
                    # full pipeline
                    rospy.wait_for_service('/scan', timeout=5.0)
                    rospy.ServiceProxy('/scan', Empty)()
                    rospy.wait_for_service('/registration', timeout=5.0)
                    rospy.ServiceProxy('/registration', Empty)()
                    rospy.wait_for_service('/reconstruction', timeout=5.0)
                    rospy.ServiceProxy('/reconstruction', Empty)()
                    if req.get("pattern"): rospy.set_param('/polishing_pattern', req["pattern"])
                    if req.get("pressure"): rospy.set_param('/polishing_pressure', req["pressure"])
                    if req.get("speed"): rospy.set_param('/polishing_speed', req["speed"])
                    rospy.wait_for_service('/tool_path_planning', timeout=5.0)
                    rospy.ServiceProxy('/tool_path_planning', Empty)()
                    rospy.wait_for_service('/interpolate', timeout=5.0)
                    rospy.ServiceProxy('/interpolate', Empty)()
                    rospy.wait_for_service('/waypoints_save', timeout=5.0)
                    rospy.ServiceProxy('/waypoints_save', Empty)()
                    pipe.send("[env] Full path generation completed.")

                elif action == "execute_path":
                    rospy.wait_for_service('/execute_path', timeout=5.0)
                    rospy.ServiceProxy('/execute_path', Empty)()
                    pipe.send("[env] Execution started.")

                else:
                    pipe.send(f"[env] Unknown action: {action}")

            except Exception as e:
                pipe.send(f"[env] {action} failed: {e}")
