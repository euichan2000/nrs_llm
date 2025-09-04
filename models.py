# models.py
def get_chatgpt_output(client, model_name, prompt, history, role="user"):
    """
    Send a prompt to the chat model and return the updated message history.
    - client: the OpenAI API client (or similar) to use for completion.
    - model_name: the model to use (e.g., "gpt-4").
    - prompt: the prompt string to send.
    - history: the list of past messages (each a dict with 'role' and 'content').
    - role: the role of the prompt message ("system" or "user").
    """
    # Append the new prompt with its role to the conversation history
    history.append({"role": role, "content": prompt})
    # Call the OpenAI ChatCompletion API (assuming client is set up accordingly)
    completion = client.chat.completions.create(
        model=model_name,
        messages=history,
        temperature=0.3,
    )
    # Get the assistant's reply
    assistant_reply = completion.choices[0].message.content
    # Append the assistant response to history
    history.append({"role": "assistant", "content": assistant_reply})
    return history
