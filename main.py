# main.py (refactored with conversation memory + pipe.recv logging)
import openai
import os
import traceback
import multiprocessing
import logging
from contextlib import redirect_stdout
from io import StringIO

from api import API
from env import run_environment
from prompts.main_prompt import MAIN_PROMPT
from prompts.error_correction_prompt import ERROR_CORRECTION_PROMPT
from prompts.print_output_prompt import PRINT_OUTPUT_PROMPT
from prompts.task_summary_prompt import TASK_SUMMARY_PROMPT
from prompts.task_failure_prompt import TASK_FAILURE_PROMPT

import models

# Initialize OpenAI API client
openai.api_key = os.getenv("OPENAI_API_KEY", "")
client = openai.OpenAI()

if __name__ == "__main__":
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(logging.INFO)

    parent_conn, child_conn = multiprocessing.Pipe()
    api = API(pipe=parent_conn, logger=logger)

    env_process = multiprocessing.Process(target=run_environment, args=(child_conn,))
    env_process.start()

    conversation_memory = []  # Accumulate long-term conversation memory across tasks

    while True:
        command = input("\nEnter a polishing command (or 'exit' to quit): ")
        if not command or command.lower() in ("exit", "quit"):
            logger.info("Exiting the robot polishing system.")
            break

        api.command = command
        api.completed = False
        task_failed = False
        completed = False

        # Inject current command into MAIN_PROMPT
        system_prompt = MAIN_PROMPT.replace("[INSERT TASK]", command)
        messages = conversation_memory.copy()  # Start from past memory
        messages.append({"role": "system", "content": system_prompt})

        messages = models.get_chatgpt_output(client, model_name="gpt-4o-mini", prompt=command, history=messages, role="user")

        while True:
            reply = messages[-1]["content"]
            print("\nAssistant:\n" + reply.strip())

            if "```python" not in reply:
                user_input = input("Your answer to the assistant (or press Enter to continue): ")
                messages = models.get_chatgpt_output(client, model_name="gpt-4o-mini", prompt=user_input, history=messages, role="user")
                continue

            code_blocks = reply.split("```python")
            block_number = 0
            for block in code_blocks[1:]:
                if "```" in block:
                    code_snippet = block.split("```", 1)[0]
                    block_number += 1
                    try:
                        f = StringIO()
                        with redirect_stdout(f):
                            exec(code_snippet, {"api": api})

                        output = f.getvalue()

                        # Also check for responses from env process
                        if parent_conn.poll():
                            env_response = parent_conn.recv()
                            print("[ENV]:", env_response)

                        if output:
                            if len(output) > 1000:
                                output = output[:1000] + "\n... (truncated)"
                            feedback_prompt = PRINT_OUTPUT_PROMPT.replace("[INSERT PRINT STATEMENT OUTPUT]", output)
                            messages = models.get_chatgpt_output(client, model_name="gpt-4o-mini", prompt=feedback_prompt, history=messages, role="user")

                        if api.check_task_success():
                            completed = True
                        task_failed = not completed
                    except Exception as e:
                        error_trace = traceback.format_exc()
                        logger.error(f"Error in code block {block_number}: {e}")
                        error_prompt = ERROR_CORRECTION_PROMPT.replace("[INSERT BLOCK NUMBER]", str(block_number)) \
                                                              .replace("[INSERT ERROR MESSAGE]", error_trace)
                        messages = models.get_chatgpt_output(client, model_name="gpt-4o-mini", prompt=error_prompt, history=messages, role="user")
                        task_failed = True
                        break

            if task_failed and not completed:
                logger.info("[FAIL] The task did not complete successfully. Gathering summary for retry...")
                summary_request = TASK_SUMMARY_PROMPT.replace("[INSERT TASK]", command)
                messages = models.get_chatgpt_output(client, model_name="gpt-4o-mini", prompt=summary_request, history=messages, role="user")
                task_summary = messages[-1]["content"]

                retry_system_prompt = MAIN_PROMPT.replace("[INSERT TASK]", command)
                retry_system_prompt += "\n" + TASK_FAILURE_PROMPT.replace("[INSERT TASK SUMMARY]", task_summary)
                logger.info("[RETRY] Prompting the LLM to re-plan and retry the task...")
                messages = conversation_memory.copy()
                messages.append({"role": "system", "content": retry_system_prompt})
                messages = models.get_chatgpt_output(client, model_name="gpt-4o-mini", prompt=command, history=messages, role="user")
                task_failed = False
                completed = False
                continue

            if completed:
                logger.info("[SUCCESS] The polishing task was completed successfully.")
                break

        conversation_memory.extend(messages)

    env_process.terminate()
    env_process.join()
