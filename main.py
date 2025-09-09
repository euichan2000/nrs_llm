# main.py (minimal, robot_control_prompt 전용)
import openai
import os
import traceback
import multiprocessing
import logging
from contextlib import redirect_stdout
from io import StringIO
import time

from api import API
from env import run_environment
from prompts.robot_control_prompt import ROBOT_CONTROL_PROMPT
import models

# Initialize OpenAI API client
openai.api_key = os.getenv("OPENAI_API_KEY", "")
client = openai.OpenAI()

MODEL_NAME = os.getenv("LLM_MODEL", "gpt-4o-mini")

if __name__ == "__main__":
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(logging.INFO)

    parent_conn, child_conn = multiprocessing.Pipe()
    api = API(pipe=parent_conn, logger=logger)

    env_process = multiprocessing.Process(target=run_environment, args=(child_conn,))
    env_process.start()

    try:
        while True:
            command = input("\nEnter a robot command (or 'exit' to quit): ").strip()
            if not command or command.lower() in ("exit", "quit"):
                logger.info("Exiting.")
                break

            # 상태 초기화
            api.command = command
            api.completed = False
            try:
                # 과도한 과거 메모리, 오류 교정, 요약 전부 제거
                # 오직 시스템 프롬프트 1개 + 유저 메시지 1개
                messages = [
                    {"role": "system", "content": ROBOT_CONTROL_PROMPT},
                    {"role": "user", "content": command},
                ]

                # LLM 호출
                messages = models.get_chatgpt_output(
                client,
                model_name=MODEL_NAME,
                system_prompt=ROBOT_CONTROL_PROMPT,
                user_cmd=command,
                temperature=0.2,
                )

                reply = messages[-1]["content"]
                print("\nAssistant:\n" + reply.strip())

                # 코드블록 추출
                if "```python" not in reply:
                    print("[WARN] 코드블록을 찾지 못했음. 프롬프트를 점검하세요.")
                    continue

                # 여러 블록이 와도 첫 블록만 실행
                code_snippet = reply.split("```python", 1)[1].split("```", 1)[0]

                # 코드 실행
                f = StringIO()
                try:
                    with redirect_stdout(f):
                        # 실행 환경에 api와 __USER_MESSAGE__를 제공
                        exec(code_snippet, {"api": api, "__USER_MESSAGE__": command})
                except Exception as e:
                    error_trace = traceback.format_exc()
                    print("[EXEC-ERROR]\n", error_trace)
                    continue
                finally:
                    output = f.getvalue()
                    if output:
                        print("[PRINT]:")
                        print(output if len(output) < 2000 else output[:2000] + "\n... (truncated)")

                # env 메시지 비우기
                t0 = time.time()
                while time.time() - t0 < 1.0:
                    if parent_conn.poll():
                        env_response = parent_conn.recv()
                        api.ingest_env_message(env_response)   # ← 이 줄 추가
                        print("[ENV]:", env_response)
                    else:
                        time.sleep(0.05)

                # 성공 판정
                if hasattr(api, "check_task_success") and api.check_task_success():
                    logger.info("[SUCCESS] Task completed.")
                elif getattr(api, "completed", False):
                    logger.info("[SUCCESS] Marked completed.")
                else:
                    logger.info("[INFO] Not marked as completed. Check robot/logs.")

            except KeyboardInterrupt:
                print("\nInterrupted by user.")
                break
            except Exception as e:
                print("[FATAL ERROR]:", e)
                print(traceback.format_exc())
                break

    finally:
        env_process.terminate()
        env_process.join()
