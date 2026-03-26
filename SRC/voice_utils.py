# SRC/utils/sarvam_multilingual.py
import os
import base64
import re
import requests
from dotenv import load_dotenv

# Ensure .env variables are available even if caller didn't load them yet.
load_dotenv()

SARVAM_BASE_URL = "https://api.sarvam.ai"


def _get_sarvam_api_key() -> str:
    key = (
        os.getenv("SARVAM_API_KEY")
        or os.getenv("SARVAM_API_SUBSCRIPTION_KEY")
        or ""
    ).strip()
    if not key:
        raise RuntimeError(
            "Missing SARVAM_API_KEY (or SARVAM_API_SUBSCRIPTION_KEY) in .env"
        )
    return key


def _headers_json() -> dict:
    return {
        "api-subscription-key": _get_sarvam_api_key(),
        "Content-Type": "application/json",
    }

# ✅ Only allow codes Sarvam translate supports (docs list)
ALLOWED_LANGS = {
    "as-IN","bn-IN","brx-IN","doi-IN","en-IN","gu-IN","hi-IN","kn-IN","kok-IN","ks-IN",
    "mai-IN","ml-IN","mni-IN","mr-IN","ne-IN","od-IN","pa-IN","sa-IN","sat-IN","sd-IN",
    "ta-IN","te-IN","ur-IN"
}

def _safe_lang(code: str | None, default: str = "en-IN") -> str:
    if not code:
        return default
    code = code.strip()
    if code == "auto":
        return "auto"
    return code if code in ALLOWED_LANGS else default

def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """
    Splits into chunks <= max_chars with basic sentence boundaries.
    """
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []

    # Split by sentence-ish boundaries
    parts = re.split(r"(?<=[\.\!\?\n])\s+", text)
    chunks, buf = [], ""

    for p in parts:
        if not p:
            continue
        if len(buf) + len(p) + 1 <= max_chars:
            buf = (buf + " " + p).strip()
        else:
            if buf:
                chunks.append(buf)
            # if single part itself too big, hard split
            while len(p) > max_chars:
                chunks.append(p[:max_chars])
                p = p[max_chars:]
            buf = p.strip()

    if buf:
        chunks.append(buf)
    return chunks

def translate_text_once(
    text: str,
    target_lang: str,
    source_lang: str = "auto",
    model: str = "mayura:v1",
    mode: str = "formal",
) -> dict:
    """
    Single call translate. Raises with detailed error body on failure.
    Endpoint: POST https://api.sarvam.ai/translate :contentReference[oaicite:1]{index=1}
    """
    url = f"{SARVAM_BASE_URL}/translate"

    payload = {
        "input": text,
        "source_language_code": source_lang,
        "target_language_code": target_lang,
        "model": model,
        "mode": mode,
    }

    r = requests.post(url, headers=_headers_json(), json=payload, timeout=60)

    if not r.ok:
        # show Sarvam error body for debugging
        raise RuntimeError(f"Sarvam translate failed: {r.status_code} {r.text}")

    return r.json()

def translate_text_smart(text: str, target_lang: str, source_lang: str = "auto") -> dict:
    """
    Smart translate:
    - Validates language codes
    - Uses mayura:v1 for short text (<=1000)
    - Uses sarvam-translate:v1 for longer text (<=2000)
    - Chunks if needed
    """
    target_lang = _safe_lang(target_lang, default="en-IN")
    source_lang = "auto" if source_lang == "auto" else _safe_lang(source_lang, default="en-IN")

    text = (text or "").strip()
    if not text:
        return {"translated_text": "", "source_language_code": source_lang if source_lang != "auto" else "unknown"}

    # Decide model by length
    if len(text) <= 1000:
        model, mode, max_chars = "mayura:v1", "code-mixed", 1000
    else:
        model, mode, max_chars = "sarvam-translate:v1", "formal", 2000

    chunks = _split_into_chunks(text, max_chars=max_chars)
    out_chunks = []
    detected = None

    for ch in chunks:
        resp = translate_text_once(
            text=ch,
            target_lang=target_lang,
            source_lang=source_lang,
            model=model,
            mode=mode,
        )
        out_chunks.append(resp.get("translated_text", ch))
        detected = detected or resp.get("source_language_code")

    return {
        "translated_text": "\n".join(out_chunks).strip(),
        "source_language_code": detected or (source_lang if source_lang != "auto" else "unknown")
    }

def to_english(user_text: str) -> tuple[str, str]:
    resp = translate_text_smart(user_text, target_lang="en-IN", source_lang="auto")
    return resp.get("translated_text", user_text), resp.get("source_language_code", "unknown")

def from_english(english_text: str, target_lang: str) -> str:
    target_lang = _safe_lang(target_lang, default="en-IN")
    if target_lang == "en-IN":
        return english_text
    resp = translate_text_smart(english_text, target_lang=target_lang, source_lang="en-IN")
    return resp.get("translated_text", english_text)


def _detect_audio_mime_and_ext(b: bytes) -> tuple[str, str]:
    """
    Detect common audio container from magic bytes.
    Returns (mime, ext)
    """
    if not b:
        return "application/octet-stream", "bin"

    # WAV: RIFF....WAVE
    if len(b) >= 12 and b[0:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "audio/wav", "wav"

    # WEBM/Matroska: 1A 45 DF A3
    if b[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm", "webm"  # Sarvam accepts audio/webm / video/webm

    # OGG: OggS
    if b[:4] == b"OggS":
        return "audio/ogg", "ogg"

    # MP3: ID3 or frame sync FF FB / FF F3 / FF F2
    if b[:3] == b"ID3" or (len(b) >= 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0):
        return "audio/mpeg", "mp3"

    # AAC ADTS often starts with FFF1/FFF9
    if len(b) >= 2 and b[0] == 0xFF and (b[1] & 0xF6) in (0xF0, 0xF8):
        return "audio/aac", "aac"

    return "application/octet-stream", "bin"


def stt_translate_audio(file_bytes: bytes, filename: str | None = None, model: str = "saaras:v2.5") -> dict:
    """
    Speech -> English directly (Sarvam STT Translate)
    FIX: Always send correct MIME type so Sarvam doesn't see 'None'
    """
    url = f"{SARVAM_BASE_URL}/speech-to-text-translate"
    headers = {"api-subscription-key": _get_sarvam_api_key()}

    mime, ext = _detect_audio_mime_and_ext(file_bytes)
    if not filename:
        filename = f"audio.{ext}"

    # ✅ IMPORTANT: provide (filename, bytes, mime)
    files = {"file": (filename, file_bytes, mime)}
    data = {"model": model}

    r = requests.post(url, headers=headers, files=files, data=data, timeout=120)
    if not r.ok:
        raise RuntimeError(f"Sarvam STT translate failed: {r.status_code} {r.text}")
    return r.json()


def tts_audio_base64(
    text: str, target_lang: str,
    model: str = "bulbul:v3",
    speaker: str = "shubh",
    sample_rate: int = 24000,
) -> bytes:
    target_lang = _safe_lang(target_lang, default="en-IN")
    allowed_speakers = {
        "anushka","abhilash","manisha","vidya","arya","karun","hitesh","aditya","ritu","priya",
        "neha","rahul","pooja","rohan","simran","kavya","amit","dev","ishita","shreya","ratan",
        "varun","manan","sumit","roopa","kabir","aayan","shubh","ashutosh","advait","amelia",
        "sophia","anand","tanya","tarun","sunny","mani","gokul","vijay","shruti","suhani",
        "mohit","kavitha","rehan","soham","rupali"
    }
    speaker = (speaker or "shubh").strip().lower()
    if speaker not in allowed_speakers:
        speaker = "shubh"

    url = f"{SARVAM_BASE_URL}/text-to-speech"
    payload = {
        "text": text,
        "target_language_code": target_lang,
        "model": model,
        "speaker": speaker,
        "sample_rate": sample_rate,
    }

    r = requests.post(url, headers=_headers_json(), json=payload, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Sarvam TTS failed: {r.status_code} {r.text}")

    out = r.json()
    b64 = out["audios"][0]
    return base64.b64decode(b64)


def process_voice_input(audio_bytes: bytes, lang_code: str):
    """
    Backward-compatible wrapper for scheme tab:
    returns (local_text, english_text).
    """
    resp = stt_translate_audio(audio_bytes)

    local_text = (
        resp.get("transcript")
        or resp.get("text")
        or resp.get("input")
        or ""
    )
    english_text = (
        resp.get("translated_text")
        or resp.get("translation")
        or ""
    )

    local_text = str(local_text).strip()
    english_text = str(english_text).strip()

    if not english_text and local_text:
        english_text, _ = to_english(local_text)

    if not local_text:
        local_text = english_text

    return local_text, english_text


def generate_voice_output(english_text: str, lang_code: str, lang_name: str):
    """
    Backward-compatible wrapper for scheme tab:
    returns (localized_text, audio_bytes).
    """
    local_text = from_english(english_text, target_lang=lang_code)
    audio_bytes = tts_audio_base64(local_text, target_lang=lang_code)
    return local_text, audio_bytes
