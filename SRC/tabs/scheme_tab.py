import streamlit as st
import json
from streamlit_mic_recorder import mic_recorder

from SRC.tools.hyper_browser_tool import HyperBrowseGeneralTool
from SRC.tools.gemini_response_tool import GeminiResponseTool

from SRC.voice_utils import (
    to_english,
    from_english,
    stt_translate_audio,
    tts_audio_base64,
)

SUPPORTED_LANGS = {
    "Auto (detect)": "auto",
    "English": "en-IN",
    "Hindi": "hi-IN",
    "Punjabi": "pa-IN",
    "Marathi": "mr-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
    "Bengali": "bn-IN",
    "Gujarati": "gu-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Odia": "od-IN",
    "Urdu": "ur-IN",
}


def render():
    # --- HEADER SECTION WITH HELP TIP ---
    col1, col2 = st.columns([0.9, 0.1])

    with col1:
        st.title("🏛️ Government Scheme Finder")
        st.markdown("Find official government schemes, subsidies, and loan details verified from government websites.")

    with col2:
        with st.popover("ℹ️ Help"):
            st.markdown("""
            ### How to use this tab:
            1. **Query:** Type what you are looking for (e.g., "Kisan Credit Card", "Solar Pump Subsidy").
            2. **State:** (Optional) Enter your state to find local schemes (e.g., "Rajasthan").
            3. **Mode:**
               - `Gov Only`: Searches ONLY official government websites (.gov.in). Best for trust.
               - `Auto`: Searches everything but prefers reliable sources.
            4. **Max Sources:** How many websites to read (Default 3 is usually enough).

            **What you get:**
            - A summarized answer grounded in evidence.
            - Direct links to official application forms.
            - Eligibility criteria and deadlines.
            """)

    st.divider()

    # --- SESSION INIT ---
    if "user_lang_code" not in st.session_state:
        st.session_state["user_lang_code"] = "en-IN"

    # Persist results so they DON'T disappear on rerun (Hear click etc.)
    if "scheme_last_answer_user" not in st.session_state:
        st.session_state["scheme_last_answer_user"] = ""
    if "scheme_last_sources" not in st.session_state:
        st.session_state["scheme_last_sources"] = []
    if "scheme_last_user_lang" not in st.session_state:
        st.session_state["scheme_last_user_lang"] = "en-IN"

    # ✅ NEW: Voice auto-run flags
    if "scheme_voice_autorun" not in st.session_state:
        st.session_state["scheme_voice_autorun"] = False
    if "scheme_last_audio_size" not in st.session_state:
        st.session_state["scheme_last_audio_size"] = 0

    # --- INPUT SECTION (keeps your original inputs) ---
    with st.container(border=True):
        col_q, col_loc = st.columns([2, 1])

        with col_q:
            query = st.text_input(
                "🔍 What scheme are you looking for?",
                placeholder="e.g. Subsidy for tractor, KCC loan..."
            )

        with col_loc:
            location = st.text_input(
                "📍 State / District (Optional)",
                placeholder="e.g. Rajasthan"
            )

        # Language + voice input
        col_l1, col_l2 = st.columns([1, 1])
        with col_l1:
            lang_choice = st.selectbox("🌐 Reply language", list(SUPPORTED_LANGS.keys()), index=0)
        with col_l2:
            st.caption("🎙️ Voice query (optional)")
            audio = mic_recorder(start_prompt="🎤 Speak", stop_prompt="⏹ Stop", key="scheme_mic")

        # ✅ Extract audio bytes (supports multiple mic_recorder versions)
        audio_bytes = None
        if audio:
            audio_bytes = audio.get("bytes") or audio.get("audio") or audio.get("data")

        # ✅ Auto-run when NEW audio arrives (Stop pressed)
        if audio_bytes:
            cur_size = len(audio_bytes)
            if cur_size != st.session_state.get("scheme_last_audio_size", 0):
                st.session_state["scheme_last_audio_size"] = cur_size
                st.session_state["scheme_voice_autorun"] = True

        with st.expander("⚙️ Advanced Settings"):
            col_m, col_s = st.columns(2)
            with col_m:
                mode = st.selectbox(
                    "Search Mode",
                    ["gov_only", "auto", "general"],
                    index=0,
                    help="'gov_only' restricts results to official .gov.in websites."
                )
            with col_s:
                max_sources = st.slider("Max Websites to Scan", min_value=1, max_value=5, value=3)

        search_btn = st.button("🚀 Find Schemes", type="primary", use_container_width=True)

    # Decide language code
    selected_lang_code = SUPPORTED_LANGS.get(lang_choice, "auto")
    if selected_lang_code != "auto":
        st.session_state["user_lang_code"] = selected_lang_code

    # ✅ Trigger either by button OR by voice stop
    trigger_run = search_btn or st.session_state.get("scheme_voice_autorun", False)

    # --- EXECUTION LOGIC ---
    if trigger_run and (query or audio_bytes):
        status_container = st.status("🕵️ searching government databases...", expanded=True)

        try:
            # ✅ Reset autorun so it doesn't loop
            st.session_state["scheme_voice_autorun"] = False

            detected_lang = None

            # 0) VOICE PATH (auto-trigger on Stop)
            if audio_bytes:
                status_container.write("🎙️ Converting speech → English (Sarvam STT Translate)...")
                stt_resp = stt_translate_audio(audio_bytes, filename="scheme_audio.wav")

                query_en = (stt_resp.get("transcript") or stt_resp.get("text") or "").strip()
                detected_lang = stt_resp.get("language_code") or stt_resp.get("source_language_code")

                if not query_en:
                    status_container.update(label="❌ Could not understand audio", state="error")
                    st.error("Could not transcribe audio. Please try again.")
                    return

                st.info(f"🗣️ Heard (English): {query_en}")

                if selected_lang_code == "auto" and detected_lang and str(detected_lang).endswith("-IN"):
                    st.session_state["user_lang_code"] = detected_lang

            # 1) TEXT PATH
            else:
                status_container.write("🌐 Detecting language + translating query → English...")
                query_en, detected_lang_text = to_english(query)

                if selected_lang_code == "auto" and detected_lang_text and str(detected_lang_text).endswith("-IN"):
                    st.session_state["user_lang_code"] = detected_lang_text

            status_container.write(f"✅ Working in English internally: **{query_en}**")

            # 2) BROWSE STEP
            status_container.write("🌐 Browsing official portals...")
            browse_tool = HyperBrowseGeneralTool()

            browse_result_json = browse_tool.run({
                "query": query_en,
                "location_hint": location,
                "mode": mode,
                "max_sources": max_sources
            })

            browse_data = json.loads(browse_result_json)

            if browse_data.get("status") != "ok":
                status_container.update(label="❌ Search Failed", state="error")
                st.error(f"Search Error: {browse_data.get('message')}")
                return

            sources = browse_data.get("sources", [])
            status_container.write(f"✅ Found {len(sources)} relevant sources.")

            # 3) GENERATE ANSWER STEP
            status_container.write("🧠 Analyzing eligibility criteria...")
            gemini_tool = GeminiResponseTool()

            gemini_inp = {
                "query": query_en,
                "intent": browse_data.get("data", {}).get("intent", "general"),
                "evidence_lines": browse_data.get("data", {}).get("evidence_lines", []),
                "schemes": browse_data.get("data", {}).get("schemes"),
                "sources": sources,
            }

            gemini_result_json = gemini_tool.run(gemini_inp)
            gemini_data = json.loads(gemini_result_json)

            status_container.update(label="✅ Verified Information Found", state="complete", expanded=False)

            if gemini_data.get("status") == "ok":
                answer_en = gemini_data.get("data", {}).get("answer", "")

                user_lang = st.session_state.get("user_lang_code", "en-IN")
                answer_user = from_english(answer_en, user_lang)

                # STORE result for persistence
                st.session_state["scheme_last_answer_user"] = answer_user
                st.session_state["scheme_last_sources"] = sources
                st.session_state["scheme_last_user_lang"] = user_lang
            else:
                st.error("Could not generate summary. Please try again.")

        except Exception as e:
            status_container.update(label="❌ System Error", state="error")
            st.error(f"An error occurred: {str(e)}")

    # --- PERSISTENT RESULT RENDERING ---
    last_answer = st.session_state.get("scheme_last_answer_user", "")
    last_sources = st.session_state.get("scheme_last_sources", [])
    last_lang = st.session_state.get("scheme_last_user_lang", st.session_state.get("user_lang_code", "en-IN"))

    if last_answer:
        st.markdown("### 📋 Scheme Details")
        st.markdown(last_answer)

        c1, c2 = st.columns([0.2, 0.8])

        with c1:
            if st.button("🔊 Hear", key="scheme_hear_btn", use_container_width=True):
                try:
                    with st.spinner("Generating voice..."):
                        MAX_TTS_CHARS = 1200
                        tts_text = last_answer if len(last_answer) <= MAX_TTS_CHARS else (last_answer[:MAX_TTS_CHARS] + "...")
                        audio_bytes_out = tts_audio_base64(tts_text, target_lang=last_lang)

                    # If audio doesn't play, try format="audio/mp3"
                    st.audio(audio_bytes_out, format="audio/wav")

                except Exception as e:
                    st.error(f"TTS Error: {str(e)}")

        with c2:
            st.caption(f"Reply language: {last_lang}")

        if last_sources:
            st.markdown("---")
            st.caption("🔗 Verified Sources:")
            cols = st.columns(min(len(last_sources), 6))
            for idx, link in enumerate(last_sources[:6]):
                display_text = link.replace("https://", "").replace("http://", "").split("/")[0]
                cols[idx % len(cols)].link_button(f"🔗 {display_text}", link)
