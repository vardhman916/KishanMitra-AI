import re
import os
import requests

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from irrigation_advisor.sprinkler.engine_csv import SprinklerCSVEngine
from irrigation_advisor.sprinkler.rag_engine import SprinklerRAG
from irrigation_advisor.drip.engine_csv import DripCSVEngine
from irrigation_advisor.drip.rag_engine import DripRAG
from irrigation_advisor.web_fallback_serper import SerperWebFallbackEngine
from streamlit_mic_recorder import mic_recorder
import tempfile
import openai

import requests
import tempfile
import os
import streamlit as st

def speech_to_text(audio_bytes):
    try:
        # Get API key
        try:
            sarvam_api_key = st.secrets.get("SARVAM_API_KEY")
        except:
            sarvam_api_key = os.getenv("SARVAM_API_KEY")

        if not sarvam_api_key:
            raise ValueError("Missing SARVAM_API_KEY")

        # Save audio temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        url = "https://api.sarvam.ai/speech-to-text"

        data = {
            "language_code": "unknown"   # auto-detect language
        }

        headers = {
            "api-subscription-key": sarvam_api_key
        }

        # Some recorders produce webm, others wav/mp3. Try common mime types.
        mime_candidates = [
            "audio/wav",
            "audio/webm",
            "audio/mpeg",
            "audio/mp4",
            "audio/ogg",
            "audio/flac",
            "application/octet-stream",
        ]

        last_resp = None
        for mime in mime_candidates:
            with open(tmp_path, "rb") as f:
                files = {"file": (os.path.basename(tmp_path), f, mime)}
                try:
                    response = requests.post(url, files=files, data=data, headers=headers, timeout=30)
                except Exception as e:
                    last_resp = e
                    continue

            if getattr(response, "status_code", None) == 200:
                return response.json().get("transcript", "")
            last_resp = response

        # If all attempts failed, return last response text or exception
        if isinstance(last_resp, Exception):
            return f"STT failed: {str(last_resp)}"
        return f"STT failed: {getattr(last_resp, 'text', str(last_resp))}"

    except Exception as e:
        return f"Speech recognition failed: {str(e)}"


def _init_sprinkler_csv_engine():
    if "sprinkler_csv" not in st.session_state:
        st.session_state.sprinkler_csv = SprinklerCSVEngine(
            "irrigation_advisor/sprinkler/data/sprinkler_cost.csv",
            "irrigation_advisor/sprinkler/data/crop_response_sprinkler.csv",
            "irrigation_advisor/sprinkler/data/crop_water_requirement.csv",
        )
    return st.session_state.sprinkler_csv

def _init_drip_csv_engine():
    if "drip_csv" not in st.session_state:
        st.session_state.drip_csv = DripCSVEngine(
            "irrigation_advisor/drip/data/drip_cost.csv",
            "irrigation_advisor/drip/data/crop_response_drip.csv",
        )
    return st.session_state.drip_csv

def translate_with_sarvam(text, target_lang):
    """
    Translate English text into target language using Sarvam AI API.
    """

    # Get API key
    try:
        sarvam_api_key = st.secrets.get("SARVAM_API_KEY")
    except:
        sarvam_api_key = os.getenv("SARVAM_API_KEY")

    if not sarvam_api_key:
        raise ValueError("Missing SARVAM_API_KEY")

    url = "https://api.sarvam.ai/translate"

    payload = {
        "input": text,
        # let the API auto-detect source language when translating into target
        "source_language_code": "auto",
        "target_language_code": target_lang,
    }

    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": sarvam_api_key
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        return response.json().get("translated_text", "")
    else:
        # return response details for easier debugging in UI
        try:
            err = response.json()
        except Exception:
            err = response.text
        return f"Translation failed: {err}"


def _init_drip_rag_engine():
    if "drip_rag" not in st.session_state:
        gemini_api_key = None
        try:
            gemini_api_key = (
                st.secrets.get("GEMINI_API_KEY1")
                or st.secrets.get("GEMINI_API_KEY1")
            )
        except StreamlitSecretNotFoundError:
            gemini_api_key = None

        if not gemini_api_key:
            gemini_api_key = os.getenv("GEMINI_API_KEY1") or os.getenv("GEMINI_API_KEY1")

        if not gemini_api_key:
            raise ValueError(
                "Missing Gemini API key. Add GEMINI_API_KEY1 (or GEMINI_API_KEY1)."
            )

        st.session_state.drip_rag = DripRAG(
            "irrigation_advisor/drip/data/drip_irrigation.pdf",
            gemini_api_key=gemini_api_key,
        )

    return st.session_state.drip_rag

def _init_web_engine():
    if "web_engine" not in st.session_state:
        # Gemini key
        gemini_api_key = None
        try:
            gemini_api_key = (
                st.secrets.get("GEMINI_API_KEY1")
                or st.secrets.get("GEMINI_API_KEY1")
            )
        except StreamlitSecretNotFoundError:
            gemini_api_key = None

        if not gemini_api_key:
            gemini_api_key = (
                os.getenv("GEMINI_API_KEY1")
                or os.getenv("GEMINI_API_KEY1")
            )

        # Serper key
        try:
            serper_api_key = st.secrets.get("SERPER_API_KEY")
        except:
            serper_api_key = os.getenv("SERPER_API_KEY")

        if not gemini_api_key:
            raise ValueError("Missing Gemini API key.")

        if not serper_api_key:
            raise ValueError("Missing SERPER_API_KEY.")

        st.session_state.web_engine = SerperWebFallbackEngine(
            gemini_api_key,
            serper_api_key
        )

    return st.session_state.web_engine

def display_answer_with_translation(answer_text, widget_prefix):
    # Show English Answer
    st.markdown("### English Answer")
    st.write(answer_text)

    # Language mapping
    language_map = {
        "Hindi": "hi-IN",
        "Gujarati": "gu-IN",
        "Tamil": "ta-IN",
        "Telugu": "te-IN",
        "Marathi": "mr-IN",
        "Kannada": "kn-IN",
        "Punjabi": "pa-IN",
        "Bengali": "bn-IN",
        "Odia": "od-IN",
        "Malayalam": "ml-IN",
        "Assamese": "as-IN"
    }

    selected_language = st.selectbox(
        "Select farmer-friendly language:",
        ["None"] + list(language_map.keys()),
        key=f"{widget_prefix}_language_selector"
    )

    translated_text_key = f"{widget_prefix}_translated_text"
    translated_lang_key = f"{widget_prefix}_translated_lang"
    last_answer_key = f"{widget_prefix}_last_english_answer"

    if translated_text_key not in st.session_state:
        st.session_state[translated_text_key] = None
    if translated_lang_key not in st.session_state:
        st.session_state[translated_lang_key] = None
    if last_answer_key not in st.session_state:
        st.session_state[last_answer_key] = None

    # Clear translation cache only when English answer changes
    if st.session_state[last_answer_key] != answer_text:
        st.session_state[translated_text_key] = None
        st.session_state[translated_lang_key] = None
        st.session_state[last_answer_key] = answer_text

    if selected_language != "None" and st.button("Translate", key=f"{widget_prefix}_translate_btn"):
        with st.spinner("Translating..."):
            st.session_state[translated_text_key] = translate_with_sarvam(
                answer_text,
                language_map[selected_language]
            )
            st.session_state[translated_lang_key] = selected_language

    if (
        st.session_state[translated_text_key]
        and st.session_state[translated_lang_key] == selected_language
    ):
        st.markdown("### Farmer-Friendly Version")
        st.write(st.session_state[translated_text_key])


def _init_sprinkler_rag_engine():
    if "sprinkler_rag" not in st.session_state:
        gemini_api_key = None
        try:
            gemini_api_key = (
                st.secrets.get("GEMINI_API_KEY1")
                or st.secrets.get("GEMINI_API_KEY1")
            )
        except StreamlitSecretNotFoundError:
            gemini_api_key = None

        if not gemini_api_key:
            gemini_api_key = os.getenv("GEMINI_API_KEY1") or os.getenv("GEMINI_API_KEY1")

        if not gemini_api_key:
            raise ValueError(
                "Missing Gemini API key. Add GEMINI_API_KEY1 (or GEMINI_API_KEY1) "
                "in .streamlit/secrets.toml or .env."
            )
        st.session_state.sprinkler_rag = SprinklerRAG(
            "irrigation_advisor/sprinkler/data/spring_irrigation.pdf",
            gemini_api_key=gemini_api_key,
        )
    return st.session_state.sprinkler_rag

import re

# Simple number word mapping
word_to_num = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10
}

def _extract_hectare(question):
    question = question.lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ha|hectare|hectares)\b", question.lower())
    if match:
        return float(match.group(1))

    for word, num in word_to_num.items():
        pattern = rf"\b{word}\s*(ha|hectare|hectares)\b"
        if re.search(pattern, question):
            return float(num)
    return None


def translate_to_english(text):
    """
    Convert ANY language input into English before processing.
    """
    try:
        translated = translate_with_sarvam(text, "en-IN")
        return translated if translated else text
    except Exception:
        return text  # fallback if translation fails
def _extract_crop(question, csv_engine):
    question_words = set(re.findall(r"[a-zA-Z]+", question.lower()))
    crops = set(csv_engine.response_df["crop"].tolist())
    if hasattr(csv_engine, "water_df"):
        crops |= set(csv_engine.water_df["crop"].tolist())
    matches = [crop for crop in crops if crop in question_words]
    return matches[0] if matches else None

def _is_insufficient_rag_answer(answer):
    if not answer:
        return True

    text = str(answer).strip().lower()
    insufficiency_markers = [
        "i do not have enough information in the document",
        "not enough information",
        "insufficient information",
        "not present in the context",
        "cannot answer from the context",
        "don't have enough information",
    ]
    return any(marker in text for marker in insufficiency_markers)


def _answer_from_csv(question, csv_engine):
    q = question.lower()
    is_cost_query = any(token in q for token in ["cost", "price", "budget", "amount", "investment"])
    is_water_query = any(
        token in q
        for token in [
            "water requirement",
            "requirement",
            "duration",
            "days",
            "how much water",
            "water needs",
            "water need",
            "needs water",
            "need water",
            "needs",
            "need",
        ]
    )
    is_response_query = any(token in q for token in ["water saving", "yield", "increase", "response","water saving",
    "water savings",
    "save water",
    "saving percentage","efficiency","productivity","benefit","benefits","percentage","improvement","improve"])

    if is_cost_query:
        hectare = _extract_hectare(question)
        if hectare is None:
            return {
                "source": "csv",
                "answer": "Please include land area in hectare, for example: cost for 2 hectare.",
            }
        cost = csv_engine.get_cost(hectare)
        return {
            "source": "csv",
            "answer": f"Estimated sprinkler system cost for {hectare} hectare is {cost}.",
        }

    crop = _extract_crop(question, csv_engine)
    if not crop:
        return None

    if is_water_query:
        data = csv_engine.get_water_requirement(crop)
        if data:
            return {
                "source": "csv",
                "answer": (
                    f"{data['crop'].title()} needs around {data['total_water_requirement_mm']} mm "
                    f"total water in about {data['duration_days']} days."
                ),
            }
        return None

    if is_response_query:
        data = csv_engine.get_crop_response(crop)
        if data:
            return {
                "source": "csv",
                "answer": (
                    f"For {data['crop'].title()}, sprinkler may save {data['water_saving_percent']}% water "
                    f"and increase yield by {data['yield_increase_percent']}%."
                ),
            }
        return None

    return None

def _answer_from_drip_csv(question, csv_engine):
    q = question.lower()

    is_cost_query = any(token in q for token in ["cost", "price", "budget", "amount", "investment"])
    is_response_query = any(
        token in q
        for token in [
            "water saving",
            "yield",
            "increase",
            "benefit",
            "benefits",
            "percentage",
            "improvement",
            "save water",
        ]
    )

    if is_cost_query:
        hectare = _extract_hectare(question)
        if hectare is None:
            return {
                "source": "csv",
                "answer": "Please include land area in hectare. Example: cost for 2 hectare.",
            }

        cost = csv_engine.get_cost(hectare)
        return {
            "source": "csv",
            "answer": f"Estimated drip irrigation system cost for {hectare} hectare is ₹{cost}.",
        }

    crop = _extract_crop(question, csv_engine)
    if not crop:
        return None

    if is_response_query:
        data = csv_engine.get_crop_response(crop)
        if data:
            return {
                "source": "csv",
                "answer": (
                    f"For {data['crop'].title()}, drip irrigation may save "
                    f"{data['water_saving_percent']}% water and increase yield "
                    f"by {data['yield_increase_percent']}%."
                ),
            }

    return None


def _run_pipeline(question, tab_prefix, csv_answer_fn, rag_init_fn, csv_engine):
    """
    Shared pipeline: CSV → RAG → Web fallback.
    Stores result in session_state under tab_prefix keys.
    """
    csv_answer = csv_answer_fn(question, csv_engine)

    if csv_answer:
        st.session_state[f"{tab_prefix}_last_source"] = "CSV dataset"
        st.session_state[f"{tab_prefix}_last_answer"] = csv_answer["answer"]
    else:
        try:
            rag_engine = rag_init_fn()
            spinner_label = (
                "Analyzing irrigation document..."
                if tab_prefix == "sprinkler"
                else "Analyzing drip irrigation document..."
            )
            with st.spinner(spinner_label):
                answer = rag_engine.query(question)
            if not _is_insufficient_rag_answer(answer):
                st.session_state[f"{tab_prefix}_last_source"] = "Document RAG"
                st.session_state[f"{tab_prefix}_last_answer"] = answer
            else:
                web_engine = _init_web_engine()
                with st.spinner("Searching Google..."):
                    answer = web_engine.query(question)
                st.session_state[f"{tab_prefix}_last_source"] = "Google Search (Serper)"
                st.session_state[f"{tab_prefix}_last_answer"] = answer
        except Exception:
            web_engine = _init_web_engine()
            with st.spinner("Searching Google..."):
                answer = web_engine.query(question)
            st.session_state[f"{tab_prefix}_last_source"] = "Google Search (Serper)"
            st.session_state[f"{tab_prefix}_last_answer"] = answer


def show_fertilizer_tab():
    st.header("Fertilizer and Irrigation Advisor")

    # ------------------------------------------------------------------ #
    #  Init session state keys
    # ------------------------------------------------------------------ #
    for key in [
        "sprinkler_last_answer", "sprinkler_last_source",
        "drip_last_answer",      "drip_last_source",
        # Track last-processed audio bytes so we only process new recordings
        "sprinkler_last_audio",  "drip_last_audio",
    ]:
        if key not in st.session_state:
            st.session_state[key] = None

    sprinkler_tab, drip_tab = st.tabs(["Sprinkler System", "Drip System"])

    # ================================================================== #
    #  SPRINKLER TAB
    # ================================================================== #
    with sprinkler_tab:
        st.subheader("Sprinkler Irrigation Advisor")

        with st.expander("How to use this section?"):
            st.write(
                """
                🌾 What You Can Ask Here

This irrigation advisor combines **multiple agricultural datasets** and a **technical irrigation document**.

You can explore:

---

### 1️⃣ Crop Water Requirement (Dataset Based)

Ask about:
- Total water requirement of a crop
- Crop duration (days)
- Irrigation need in mm
- Water efficiency comparison

📌 Example Questions:
- What is total water requirement for rice?
- How many days does maize take to grow?
- Compare water requirement of wheat and maize.

---

### 2️⃣ Water Saving & Yield Improvement (Dataset Based)

📌 Example Questions:
- How much water can sprinkler save for maize?
- What is yield increase percentage using sprinkler irrigation?
- Which crop benefits most from sprinkler system?

---

### 3️⃣ Crop Duration & Irrigation Planning

📌 Example Questions:
- How to plan irrigation schedule for rice?
- How much water is required per growth cycle?
- Which crops require high irrigation frequency?

---

### 4️⃣ Sprinkler System Technical Knowledge (PDF Document Based - RAG)

Ask about:
- Advantages & disadvantages
- Suitability for soil types
- Installation requirements
- Maintenance practices

📌 Example Questions:
- What are advantages of sprinkler irrigation?
- Is sprinkler suitable for sandy soil?
- What are maintenance requirements of sprinkler system?
- Where is sprinkler irrigation not recommended?

---

💡 Tip: Be specific with crop names (e.g., maize, rice, wheat).
                """
            )

        st.write("🎤 Speak your question or type below:")

        # ---- Voice input -------------------------------------------- #
        audio = mic_recorder(
            start_prompt="Start Recording",
            stop_prompt="Stop Recording",
            key="sprinkler_mic"
        )

        # Only process audio when it is NEW (bytes differ from last run)
        sprinkler_voice_question = None
        if audio and audio["bytes"] != st.session_state.sprinkler_last_audio:
            st.session_state.sprinkler_last_audio = audio["bytes"]
            with st.spinner("Converting speech to text..."):
                spoken_text = speech_to_text(audio["bytes"])
            st.write(f"🗣 You said: {spoken_text}")
            translated_question = translate_with_sarvam(spoken_text, "en-IN")
            st.write(f"🌐 Translated to English: {translated_question}")
            sprinkler_voice_question = translated_question

        # ---- Text input --------------------------------------------- #
        text_question = st.text_input(
            "Or type your question:",
            key="sprinkler_question_input"
        )

        ask_clicked = st.button("Get Answer", key="sprinkler_btn")

        # ---- Decide which question to use & run pipeline -------------- #
        # Voice recording fires immediately; text requires button click.
        if sprinkler_voice_question:
            # New voice recording → run pipeline straight away
            _run_pipeline(
                sprinkler_voice_question,
                "sprinkler",
                _answer_from_csv,
                _init_sprinkler_rag_engine,
                _init_sprinkler_csv_engine(),
            )
        elif ask_clicked:
            # Button clicked → use text box (ignore any stale audio)
            if not text_question.strip():
                st.warning("Please enter a question.")
            else:
                with st.spinner("Translating to English..."):
                    translated_text = translate_to_english(text_question)

                st.write(f"🌐 Translated to English: {translated_text}")
                _run_pipeline(
                    translated_text,
                    "sprinkler",
                    _answer_from_csv,
                    _init_sprinkler_rag_engine,
                    _init_sprinkler_csv_engine(),
                )

        # ---- Display stored answer ------------------------------------ #
        if st.session_state.sprinkler_last_answer:
            st.success(f"Answer source: {st.session_state.sprinkler_last_source}")
            display_answer_with_translation(
                st.session_state.sprinkler_last_answer, "sprinkler"
            )

    # ================================================================== #
    #  DRIP TAB
    # ================================================================== #
    with drip_tab:
        st.subheader("Drip Irrigation Advisor")

        with st.expander("How to use Drip Irrigation Advisor?"):
            st.write("""
        💧 **What You Can Ask in Drip Irrigation Section**

        This section combines structured datasets and a technical irrigation document.

        You can explore the following:

        ---

        ### 1️⃣ Drip System Cost (Dataset Based)

        Ask about:
        - Installation cost
        - Budget for specific land area
        - Investment for drip system

        📌 Example Questions:
        - What is the cost of drip irrigation for 2 hectare?
        - How much investment is required for 3.5 hectare drip system?
        - Price of drip irrigation for 1 hectare land?

        ---

        ### 2️⃣ Water Saving & Yield Improvement (Dataset Based)

        Ask about:
        - Water saving percentage
        - Yield increase percentage
        - Crop productivity improvement

        📌 Example Questions:
        - How much water saving in tomato using drip?
        - What is yield increase in onion under drip irrigation?
        - Which crop gets maximum benefit from drip irrigation?
        - Percentage improvement in banana using drip?

        ---

        ### 3️⃣ Technical Knowledge About Drip Irrigation (PDF Based - RAG)

        Ask about:
        - Advantages / Benefits / Merits
        - Disadvantages / Limitations
        - Suitable soil types
        - Maintenance practices
        - Installation requirements
        - Components of drip system
        - Emitter types
        - Filtration system
        - Fertigation process

        📌 Example Questions:
        - What are advantages of drip irrigation?
        - What are disadvantages of drip system?
        - Is drip irrigation suitable for sandy soil?
        - What are maintenance requirements?
        - What is fertigation in drip irrigation?
        - Where is drip irrigation not recommended?

        ---

        💡 Tip:
        - Mention crop name clearly (e.g., tomato, onion, banana).
        - Mention land area in hectare when asking cost-related questions.
        """)

        st.write("🎤 Speak your question or type below:")

        # ---- Voice input -------------------------------------------- #
        audio = mic_recorder(
            start_prompt="Start Recording",
            stop_prompt="Stop Recording",
            key="drip_mic"
        )

        # Only process audio when it is NEW
        drip_voice_question = None
        if audio and audio["bytes"] != st.session_state.drip_last_audio:
            st.session_state.drip_last_audio = audio["bytes"]
            with st.spinner("Processing voice..."):
                spoken_text = speech_to_text(audio["bytes"])
            st.write(f"🗣 You said: {spoken_text}")
            translated_question = translate_with_sarvam(spoken_text, "en-IN")
            st.write(f"🌐 English: {translated_question}")
            drip_voice_question = translated_question

        # ---- Text input --------------------------------------------- #
        text_question = st.text_input(
            "Or type your question:",
            key="drip_question_input"
        )

        ask_clicked = st.button("Get Drip Answer", key="drip_btn")

        # ---- Decide which question to use & run pipeline -------------- #
        if drip_voice_question:
            # New voice recording → run pipeline straight away
            _run_pipeline(
                drip_voice_question,
                "drip",
                _answer_from_drip_csv,
                _init_drip_rag_engine,
                _init_drip_csv_engine(),
            )
        elif ask_clicked:
            # Button clicked → use text box
            if not text_question.strip():
                st.warning("Please enter a question.")
            else:
                with st.spinner("Translating to English..."):
                    translated_text = translate_to_english(text_question)

                st.write(f"🌐 Translated to English: {translated_text}")
                _run_pipeline(
                    translated_text,
                    "drip",
                    _answer_from_drip_csv,
                    _init_drip_rag_engine,
                    _init_drip_csv_engine(),
                )

        # ---- Display stored answer ------------------------------------ #
        if st.session_state.drip_last_answer:
            st.success(f"Answer source: {st.session_state.drip_last_source}")
            display_answer_with_translation(
                st.session_state.drip_last_answer, "drip"
            )