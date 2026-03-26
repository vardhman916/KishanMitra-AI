import os
import streamlit as st
from dotenv import load_dotenv
from SRC.voice_utils import from_english

load_dotenv()

LANGUAGE_CODE_MAP = {
    "as": "as-IN",
    "bn": "bn-IN",
    "en": "en-IN",
    "gu": "gu-IN",
    "hi": "hi-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "mr": "mr-IN",
    "or": "od-IN",
    "pa": "pa-IN",
    "ta": "ta-IN",
    "te": "te-IN",
}


def translate_text(text, target_lang):
    if not text or not str(text).strip():
        return ""

    api_key = _get_sarvam_api_key()
    if not api_key:
        return "Translation unavailable: SARVAM_API_KEY (or SARVAM_API_SUBSCRIPTION_KEY) is not configured."

    normalized_target = _normalize_lang_code(target_lang)
    if normalized_target == "en-IN":
        return str(text)

    try:
        return from_english(str(text), normalized_target)
    except Exception as e:
        print("Sarvam API Error:", e)
        return f"Translation API Error: {e}"


def _get_sarvam_api_key():
    def _non_empty(value):
        return str(value).strip() if value is not None and str(value).strip() else None

    try:
        if hasattr(st, "secrets") and "SARVAM_API_KEY" in st.secrets:
            v = _non_empty(st.secrets["SARVAM_API_KEY"])
            if v:
                return v
        if hasattr(st, "secrets") and "SARVAM_API_SUBSCRIPTION_KEY" in st.secrets:
            v = _non_empty(st.secrets["SARVAM_API_SUBSCRIPTION_KEY"])
            if v:
                return v
    except Exception:
        pass
    return _non_empty(os.getenv("SARVAM_API_KEY")) or _non_empty(os.getenv("SARVAM_API_SUBSCRIPTION_KEY"))


def _normalize_lang_code(code: str) -> str:
    code = (code or "").strip()
    if code in LANGUAGE_CODE_MAP.values():
        return code
    return LANGUAGE_CODE_MAP.get(code, "en-IN")
