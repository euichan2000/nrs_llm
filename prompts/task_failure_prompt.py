# task_failure_prompt.py
TASK_FAILURE_PROMPT = \
"""The previous polishing task failed.
[RETRY POLICY]
You may retry at most once. Do not keep retrying the same task over 3 times.
If the task fails again, report the issue to the user and ask for clarification or adjustment.

Here is a summary of what happened:
[INSERT TASK SUMMARY]

Before retrying, analyze why the previous code did not work.
If it failed due to a coding mistake (e.g., missing `api.` prefix), do not repeat the same mistake.
Instead of retrying blindly, explain the cause and ask the user a clarifying question or offer a correction strategy.

For example:
- If `get_fingertip_position()` was called without `api.`, acknowledge it and fix it.
- If the error was due to a missing topic or bad input, suggest pointing again or describe what is missing.
- If the user asked only to display the pointing coordinate, don’t retry a full polishing plan — just show the point.

Then, generate revised Python code to proceed — only if you are confident the issue is resolved.
Otherwise, ask the user for more information or assistance.The previous polishing task failed.

Here is a summary of what happened:
[INSERT TASK SUMMARY]

Before retrying, analyze why the previous code did not work.
If it failed due to a coding mistake (e.g., missing `api.` prefix), do not repeat the same mistake.
Instead of retrying blindly, explain the cause and ask the user a clarifying question or offer a correction strategy.

For example:
- If `get_fingertip_position()` was called without `api.`, acknowledge it and fix it.
- If the error was due to a missing topic or bad input, suggest pointing again or describe what is missing.

Then, generate revised Python code to proceed — only if you are confident the issue is resolved.
Otherwise, ask the user for more information or assistance.

Use API functions step by step, and wait for responses before moving on.
"""