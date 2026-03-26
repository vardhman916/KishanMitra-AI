import streamlit as st
import os
from dotenv import load_dotenv
from SRC.voice_utils import tts_audio_base64

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage

from streamlit_mic_recorder import mic_recorder
from SRC.voice_utils import (
    to_english,
    from_english,
    stt_translate_audio
)

from SRC.tools.wrapped_tools import weather_langchain_tool, market_langchain_tool

load_dotenv()

# ---------------- LANGUAGE MAP ----------------

LANG_OPTIONS = {
    "English": "en-IN",
    "Hindi": "hi-IN",
    "Punjabi": "pa-IN",
    "Gujarati": "gu-IN",
    "Marathi": "mr-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
    "Bengali": "bn-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Odia": "or-IN",
    "Urdu": "ur-IN",
}

# ---------------- UTIL ----------------

# def to_clean_text(content) -> str:
#     if isinstance(content, str):
#         return content.strip()
#     return str(content).strip()

def to_clean_text(content):

    # ✅ Case 1: String
    if isinstance(content, str):
        return content.strip()

    # ✅ Case 2: LIST (MOST IMPORTANT FIX)
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
        return "\n".join(texts).strip()

    # ✅ Case 3: Dict
    if isinstance(content, dict):
        return content.get("text", "").strip()

    # ✅ Fallback
    return str(content).strip()


def init_langchain_agent():
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY5"),
        temperature=0.3
    )

    tools = [weather_langchain_tool, market_langchain_tool]

    system_prompt = """
    You are an expert AI Farm Advisor named 'Kisan Sahayak'.

    Always respond in SIMPLE ENGLISH only.
    Keep answers short, practical, and farmer-friendly.
    """

    return create_agent(llm, tools=tools, system_prompt=system_prompt)


def _ui_messages_to_lc(messages):
    lc_messages = []
    for msg in messages:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))
    return lc_messages


def translate_to_local(text, lang_code):
    result = from_english(
        text,
        lang_code
    )
   # ✅ CLEAN OUTPUT
    if isinstance(result, dict):
        return result.get("text", "").strip()

    return str(result).strip()


# ---------------- RENDER ----------------

def render():
    st.title("🤖 AI Farm Advisor")

    # 🌐 Language Selector
    selected_lang_name = st.selectbox("🌐 Select Language", list(LANG_OPTIONS.keys()))
    selected_lang_code = LANG_OPTIONS[selected_lang_name]

    # ---------------- SESSION ----------------
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Namaste! Ask your farming question."}]

    if "agent_messages_en" not in st.session_state:
        st.session_state.agent_messages_en = [{"role": "assistant", "content": "Hello"}]

    if "advisor_audio" not in st.session_state:
        st.session_state["advisor_audio"] = None

    if "advisor_last_response_en" not in st.session_state:
        st.session_state["advisor_last_response_en"] = ""

    if "advisor_last_response_local" not in st.session_state:
        st.session_state["advisor_last_response_local"] = ""

    if "last_audio_id" not in st.session_state:
        st.session_state["last_audio_id"] = None

    # ---------------- CHAT ----------------
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ---------------- INPUT ----------------
    st.markdown("🎤 Speak your question:")
    audio = mic_recorder(start_prompt="🎤 Start", stop_prompt="⏹ Stop")

    text_prompt = st.chat_input("Type your question...")

    user_prompt = None

    # 🎤 VOICE
    if audio:
        if audio["id"] != st.session_state["last_audio_id"]:
            with st.spinner("Processing voice..."):
                stt = stt_translate_audio(audio["bytes"], "audio.wav")
                transcript = stt.get("transcript", "")

                if transcript:
                    user_prompt = transcript
                    st.session_state["last_audio_id"] = audio["id"]

    # ⌨️ TEXT
    elif text_prompt:
        user_prompt = text_prompt

    # ---------------- PROCESS ----------------
    if user_prompt:

        # Show user msg
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        # Convert to English
        prompt_en, _ = to_english(user_prompt)

        st.session_state.agent_messages_en.append(
            {"role": "user", "content": prompt_en}
        )

        # AI Response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):

                agent = init_langchain_agent()
                lc_messages = _ui_messages_to_lc(st.session_state.agent_messages_en)

                result = agent.invoke({"messages": lc_messages})

                response_en = ""
                for m in reversed(result.get("messages", [])):
                    if isinstance(m, AIMessage):
                        response_en = to_clean_text(m.content)
                        break

                if not response_en:
                    response_en = "Sorry, no answer found."

                # 🔥 Translate to selected language
                if selected_lang_code != "en-IN":
                    response_local = translate_to_local(response_en, selected_lang_code)
                    response_local = to_clean_text(response_local)   # ✅ IMPORTANT
                else:
                    response_local = response_en

                st.markdown(response_local)

                # Save
                st.session_state.messages.append(
                    {"role": "assistant", "content": response_local}
                )

                st.session_state.agent_messages_en.append(
                    {"role": "assistant", "content": response_en}
                )

                st.session_state["advisor_last_response_en"] = response_en
                st.session_state["advisor_last_response_local"] = response_local
                st.session_state["advisor_audio"] = None

    # ================= TTS =================
    if st.session_state["advisor_last_response_en"]:

        st.markdown("---")
        st.subheader("🔊 Listen to Answer")

        col1, col2 = st.columns([0.3, 0.7])

        with col1:
            if st.button("🔊 Hear Answer"):
                with st.spinner("Generating voice..."):

                    text = st.session_state.get("advisor_last_response_local") \
                           or st.session_state.get("advisor_last_response_en")

                    text = text[:1000]

                    audio = tts_audio_base64(
                        text,
                        target_lang=selected_lang_code
                    )

                    st.session_state["advisor_audio"] = audio

        with col2:
            if st.session_state["advisor_audio"]:
                st.audio(st.session_state["advisor_audio"], format="audio/wav")
            else:
                st.caption("Click button to hear answer")