# models.py
from collections import deque

# ===== 세션 상태 =====
# (user_text, assistant_text) 튜플을 최근부터 저장
HISTORY_MAX_TURNS = 8   # 전체 보관 상한(유저-어시스턴트 묶음 기준)
WINDOW_TURNS = 4        # 모델에 보낼 최근 턴 수
SUMMARY_TRIGGER = 6     # 이 턴 수를 넘기면 요약 시도

_history = deque(maxlen=HISTORY_MAX_TURNS)
_session_summary = ""


def _register_turn(user_text: str, assistant_text: str):
    """히스토리에 이번 턴 추가"""
    _history.append((user_text, assistant_text))


def _build_messages(system_prompt: str, user_cmd: str):
    """시스템 프롬프트 + (선택) 세션 요약 + 최근 N턴 + 이번 사용자 명령"""
    msgs = [{"role": "system", "content": system_prompt}]

    if _session_summary:
        msgs.append({
            "role": "system",
            "content": f"[Session summary]\n{_session_summary}"
        })

    # 최근 N턴 삽입
    for u, a in list(_history)[-WINDOW_TURNS:]:
        msgs.append({"role": "user", "content": u})
        if a:
            msgs.append({"role": "assistant", "content": a})

    # 이번 사용자 명령
    msgs.append({"role": "user", "content": user_cmd})
    return msgs


def _maybe_update_summary(client, model_name: str):
    """히스토리가 길어지면 요약을 갱신. 실패해도 조용히 무시."""
    global _session_summary
    if len(_history) < SUMMARY_TRIGGER:
        return

    # 요약 지시
    summarizer_sys = "You are a concise summarizer for a robot-control session."
    prompt = (
        "Summarize prior exchanges into at most 5 bullet points focusing on:\n"
        "1) robot/environment assumptions\n"
        "2) libraries, IPs, ports or devices in use\n"
        "3) commands or code patterns that worked\n"
        "4) known errors and fixes\n"
        "Keep it under 80 words. No code blocks."
    )

    msgs = [{"role": "system", "content": summarizer_sys}]
    for u, a in _history:
        msgs.append({"role": "user", "content": u})
        if a:
            msgs.append({"role": "assistant", "content": a})
    msgs.append({"role": "user", "content": prompt})

    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=msgs,
            temperature=0.2,
        )
        _session_summary = completion.choices[0].message.content.strip()
    except Exception:
        pass


def get_chatgpt_output(client, model_name, system_prompt, user_cmd, temperature=0.3):
    """
    시스템 프롬프트 + 세션 요약 + 최근 N턴 + 사용자 입력으로 메시지를 구성해
    한 번 호출하고, 응답과 함께 messages 리스트를 반환.
    반환된 messages의 마지막 원소가 assistant 응답.
    """
    messages = _build_messages(system_prompt, user_cmd)

    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
    )
    assistant_reply = completion.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_reply})

    # 세션 히스토리와 요약 갱신
    _register_turn(user_cmd, assistant_reply)
    _maybe_update_summary(client, model_name)

    return messages


# 선택: 세션 초기화 유틸
def reset_session():
    """히스토리와 요약 초기화"""
    global _history, _session_summary
    _history.clear()
    _session_summary = ""
