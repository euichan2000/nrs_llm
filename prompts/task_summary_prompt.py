TASK_SUMMARY_PROMPT = \
"""Summarize what actions you took to accomplish the task "[INSERT TASK]". For each step, mention:
- Which API function was called,
- What parameters were used (if any),
- Whether the function succeeded or failed.

Then briefly explain why the overall task did not complete successfully.
"""
