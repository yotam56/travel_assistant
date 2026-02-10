import json
import os
import uuid

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.title("Travel Assistant")

# Initialise session state
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar controls
if st.sidebar.button("New chat"):
    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())
    st.rerun()

show_debug = st.sidebar.toggle("Show debug trace", value=False)

STEP_LABELS = {
    "HumanMessage": "User",
    "AIMessage": "Assistant",
    "ToolMessage": "Tool result",
}


def render_debug(debug_trace):
    """Render the debug trace inside an expander."""
    with st.expander("Debug trace", expanded=False):
        for i, step in enumerate(debug_trace, 1):
            msg_type = step.get("type", "Unknown")
            label = STEP_LABELS.get(msg_type, msg_type)

            if msg_type == "AIMessage" and step.get("tool_calls"):
                calls = ", ".join(
                    f'`{tc["name"]}({json.dumps(tc.get("args", {}), ensure_ascii=False)})`'
                    for tc in step["tool_calls"]
                )
                st.markdown(f"**{i}. {label} → tool call:** {calls}")
            elif msg_type == "ToolMessage":
                tool_name = step.get("tool_name", "?")
                st.markdown(f"**{i}. {label} (`{tool_name}`):**")
                st.code(step.get("content", ""), language="json")
            else:
                st.markdown(f"**{i}. {label}:** {step.get('content', '')}")


# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if show_debug and msg.get("debug"):
            render_debug(msg["debug"])

# Chat input
if prompt := st.chat_input("Ask me anything about travel…"):
    # Show + store user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call the API
    with st.chat_message("assistant"):
        debug_trace = None
        with st.spinner("Thinking…"):
            try:
                resp = requests.post(
                    f"{API_BASE_URL}/completions",
                    json={
                        "thread_id": st.session_state.thread_id,
                        "input": prompt,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data["choices"][0]["message"]["content"]
                debug_trace = data.get("debug")
            except requests.exceptions.ConnectionError:
                reply = "Could not reach the server. Is the API running?"
            except requests.exceptions.Timeout:
                reply = "The request timed out. Please try again."
            except requests.exceptions.HTTPError as e:
                reply = f"Server error ({e.response.status_code}). Please try again later."
            except Exception as e:
                reply = f"Something went wrong: {e}"

        st.markdown(reply)
        if show_debug and debug_trace:
            render_debug(debug_trace)

    st.session_state.messages.append(
        {"role": "assistant", "content": reply, "debug": debug_trace}
    )
