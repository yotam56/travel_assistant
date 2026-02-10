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

# ── Debug rendering ──────────────────────────────────────────────────────────


def _render_step_user(step):
    """Render a HumanMessage step."""
    st.markdown(f":bust_in_silhouette: **User**")
    st.info(step.get("content", ""), icon=None)


def _render_step_tool_call(step):
    """Render an AIMessage that contains tool calls (and optional reasoning)."""
    reasoning = step.get("reasoning", "")
    if reasoning:
        st.markdown(":thought_balloon: **Agent reasoning**")
        st.caption(reasoning)

    for tc in step.get("tool_calls", []):
        name = tc["name"]
        args = tc.get("args", {})
        st.markdown(f":hammer_and_wrench: **Tool call** &mdash; `{name}`")
        if args:
            st.json(args, expanded=False)


def _render_step_tool_result(step):
    """Render a ToolMessage (tool return value)."""
    tool_name = step.get("tool_name", "unknown")
    content = step.get("content", "")
    st.markdown(f":package: **Tool result** &mdash; `{tool_name}`")
    st.code(content, language="json")


def _render_step_assistant(step):
    """Render a final AIMessage (no tool calls)."""
    st.markdown(":robot_face: **Final response**")
    st.success(step.get("content", ""))


def render_debug(debug_trace):
    """Render a structured, collapsible debug trace."""
    with st.expander("Debug trace", expanded=False):
        for i, step in enumerate(debug_trace):
            msg_type = step.get("type", "")

            if i > 0:
                st.divider()

            col_num, col_body = st.columns([0.06, 0.94])
            with col_num:
                st.markdown(f"**{i + 1}**")

            with col_body:
                if msg_type == "HumanMessage":
                    _render_step_user(step)
                elif msg_type == "AIMessage" and step.get("tool_calls"):
                    _render_step_tool_call(step)
                elif msg_type == "ToolMessage":
                    _render_step_tool_result(step)
                elif msg_type == "AIMessage":
                    _render_step_assistant(step)
                else:
                    st.markdown(f"**{msg_type}:** {step.get('content', '')}")


# ── Chat history ─────────────────────────────────────────────────────────────

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if show_debug and msg.get("debug"):
            render_debug(msg["debug"])

# ── Chat input ───────────────────────────────────────────────────────────────

if prompt := st.chat_input("Ask me anything about travel…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

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
