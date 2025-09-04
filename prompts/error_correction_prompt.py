
# error_correction_prompt.py
ERROR_CORRECTION_PROMPT = \
"""Running code block [INSERT BLOCK NUMBER] of your previous response resulted in the following error:
[INSERT ERROR MESSAGE]

Please revise the code to fix this issue. DO NOT retry the same code blindly. If the error was due to a missing `api.` prefix or invalid function call, correct that first.

Also, if the task was a simple request (e.g., showing the pointed coordinate), make sure to only call `api.get_fingertip_position()` and print it — do not execute scanning or polishing steps unnecessarily.

Then output only the fixed Python code block, without any explanation.Running code block [INSERT BLOCK NUMBER] of your previous response resulted in the following error:
[INSERT ERROR MESSAGE]

Please revise the code to fix this issue. DO NOT retry the same code blindly. If the error was due to a missing `api.` prefix or invalid function call, correct that first.

Then output only the fixed Python code block, without any explanation.
"""
