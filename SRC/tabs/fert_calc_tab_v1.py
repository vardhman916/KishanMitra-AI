import json
import streamlit as st
import streamlit.components.v1 as components

from SRC.tools.fert_calc_live_tool_v1 import FertCalcLiveToolV1
from SRC.tools.fert_ai_explainer_tool_v1 import FertAIExplainerToolV1

# ✅ TTS + translate (NO STT)
from SRC.voice_utils import tts_audio_base64, from_english

SUPPORTED_LANGS = {
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
    st.title("🌱 Fertilizer Recommendation")
    st.caption("Dropdown options come from options.json. Calculation runs live on the official calculator.")

    tool = FertCalcLiveToolV1(headless=True)

    try:
        options = tool.load_static_options()
    except Exception as e:
        st.error(str(e))
        st.info("Create: data/fert_calc_cache_v1/options.json")
        return

    crop_groups = options.get("crop_group", [])
    crop_name_by_group = options.get("crop_name_by_group", {})
    condition_by_crop = options.get("condition_by_crop", {})
    soil_types = options.get("soil_type", [])
    organic_carbon_opts = options.get("organic_carbon", [])
    p_opts = options.get("available_p", [])
    k_opts = options.get("available_k", [])

    if not crop_groups:
        st.error("options.json is missing 'crop_group' list.")
        st.json(options)
        return

    # ✅ session init (persist table + explanation + audio across reruns)
    if "fert_last_table_html" not in st.session_state:
        st.session_state["fert_last_table_html"] = None
    if "fert_last_explanation" not in st.session_state:
        st.session_state["fert_last_explanation"] = ""
    if "fert_last_lang" not in st.session_state:
        st.session_state["fert_last_lang"] = "en-IN"
    if "fert_last_audio" not in st.session_state:
        st.session_state["fert_last_audio"] = None

    # ---------------- UI ----------------
    st.subheader("✅ Inputs (must match website dropdown text)")

    crop_group = st.selectbox("Crop Group", crop_groups)

    crop_names = crop_name_by_group.get(crop_group, [])
    if not crop_names:
        st.warning(
            f"No crop names found for '{crop_group}' in options.json.\n"
            "Add it under crop_name_by_group to use this group."
        )
        crop_names = ["(No crops configured)"]

    crop_name = st.selectbox("Crop Name", crop_names)

    conditions = condition_by_crop.get(crop_name, [])
    if not conditions:
        conditions = ["General"]

    condition = st.selectbox("Condition", conditions)

    col1, col2 = st.columns(2)
    with col1:
        plants = st.number_input("Number of plants", min_value=0.0, value=1.0, step=1.0)
    with col2:
        area = st.number_input("Area", min_value=0.0, value=1.0, step=0.5)

    st.subheader("🧪 Soil Test (Optional)")
    soil_type = st.selectbox("Soil Type", ["(skip)"] + soil_types)
    organic_carbon = st.selectbox("Organic Carbon", ["(skip)"] + organic_carbon_opts)
    available_p = st.selectbox("Available Phosphorous (kg/ha)", ["(skip)"] + p_opts)
    available_k = st.selectbox("Available Potassium (kg/ha)", ["(skip)"] + k_opts)

    mode = st.radio(
        "Recommendation Type",
        options=["blanket", "soil_test"],
        format_func=lambda x: "Generate Blanket Recommendation" if x == "blanket" else "Soil Test Based Recommendation",
        horizontal=True,
    )

    def none_if_skip(x: str):
        return None if x == "(skip)" else x

    # ---------------- Main action ----------------
    if st.button("Generate Recommendation", use_container_width=True):
        with st.spinner("Running live calculation..."):
            result = tool.generate_recommendation(
                crop_group=crop_group,
                crop_name=crop_name,
                condition=condition,
                Number_of_plants=plants,
                area_value=area,
                soil_type=none_if_skip(soil_type),
                organic_carbon=none_if_skip(organic_carbon),
                available_p=none_if_skip(available_p),
                available_k=none_if_skip(available_k),
                mode=mode,
            )

        table_html = None

        # If tool returned HTML table payload, store it (do NOT only render inside button)
        try:
            payload = json.loads(result)
            if payload.get("type") == "html_table":
                table_html = payload["html"]
                st.session_state["fert_last_table_html"] = table_html
            else:
                # Keep non-table result visible too (optional: store as explanation)
                st.write(result)
        except Exception:
            st.write(result)

        # ---------------- AI Explanation (store only) ----------------
        if table_html:
            cache_key = f"{crop_group}|{crop_name}|{condition}|{plants}|{area}|{mode}|{soil_type}|{organic_carbon}|{available_p}|{available_k}"
            if "fert_ai_cache" not in st.session_state:
                st.session_state["fert_ai_cache"] = {}

            explanation = None
            if cache_key in st.session_state["fert_ai_cache"]:
                explanation = st.session_state["fert_ai_cache"][cache_key]
            else:
                with st.spinner("Generating farmer-friendly explanation..."):
                    try:
                        explainer = FertAIExplainerToolV1()
                        explanation = explainer.explain(
                            crop_group=crop_group,
                            crop_name=crop_name,
                            condition=condition,
                            plants=plants,
                            area=area,
                            mode=mode,
                            html_table=table_html,
                        )
                        st.session_state["fert_ai_cache"][cache_key] = explanation
                    except Exception as e:
                        st.error(f"AI explanation failed: {e}")
                        st.info("Check GEMINI_API_KEY in .env and install google-generativeai.")
                        explanation = None

            # Store explanation + reset audio cache
            if explanation:
                st.session_state["fert_last_explanation"] = explanation
                st.session_state["fert_last_audio"] = None

    # ✅ ALWAYS render last generated table (so it doesn't disappear on Hear click)
    last_table_html = st.session_state.get("fert_last_table_html")
    if last_table_html:
        st.subheader("📄 Output")
        html = f"""
        <style>
            table {{
                border-collapse: collapse;
                width: 100%;
                font-family: Arial, sans-serif;
                font-size: 16px;
            }}
            td, th {{
                border: 1px solid #333;
                padding: 6px;
                text-align: center;
                vertical-align: middle;
            }}
        </style>
        {last_table_html}
        """
        components.html(html, height=620, scrolling=True)

    # ✅ ALWAYS show last explanation (persistent)
    last_explanation = st.session_state.get("fert_last_explanation", "")
    if last_explanation:
        st.markdown("---")
        st.subheader("🤖 AI Explanation")
        st.markdown(last_explanation)

    # ---------------- Farmer-Friendly Translation ----------------
    st.markdown("---")
    st.subheader("🌾 Farmer-Friendly Translation")

    farmer_lang_choice = st.selectbox(
        "Select Language for Explanation",
        list(SUPPORTED_LANGS.keys()),
        index=0,
        key="fert_farmer_lang_choice"
    )

    selected_lang_code = SUPPORTED_LANGS[farmer_lang_choice]

    # session state for translated text
    if "fert_farmer_text" not in st.session_state:
        st.session_state["fert_farmer_text"] = None

    if last_explanation:
        if st.button("🌐 Convert to Farmer-Friendly Language", key="fert_translate_btn"):
            try:
                with st.spinner("Translating for farmer understanding..."):
                    if selected_lang_code == "en-IN":
                        translated_text = last_explanation
                    else:
                        translated_text = from_english(last_explanation, selected_lang_code)

                    st.session_state["fert_farmer_text"] = translated_text

                st.success("Converted successfully ✅")

            except Exception as e:
                st.error(f"Translation Error: {str(e)}")

        # Show translated output
        if st.session_state.get("fert_farmer_text"):
            st.markdown("### 🌾 Farmer-Friendly Explanation")
            st.write(st.session_state["fert_farmer_text"])

    else:
        st.info("Generate recommendation first to translate explanation.")

    # ---------------- TTS (NO STT) ----------------
    st.markdown("---")
    st.subheader("🔊 Listen to Explanation (TTS)")

    tts_lang_choice = st.selectbox(
        "Voice Language",
        list(SUPPORTED_LANGS.keys()),
        index=0,
        key="fert_tts_lang_choice"
    )
    st.session_state["fert_last_lang"] = SUPPORTED_LANGS[tts_lang_choice]

    if last_explanation:
        colA, colB = st.columns([0.25, 0.75])
        with colA:
            if st.button("🔊 Hear Explanation", key="fert_hear_btn", use_container_width=True):
                try:
                    with st.spinner("Generating voice..."):
                        user_lang = st.session_state["fert_last_lang"]

                        # Translate explanation text for non-English voice
                        text_to_speak = last_explanation
                        if user_lang != "en-IN":
                            text_to_speak = from_english(last_explanation, user_lang)

                        MAX_TTS_CHARS = 1200
                        text_to_speak = text_to_speak if len(text_to_speak) <= MAX_TTS_CHARS else (text_to_speak[:MAX_TTS_CHARS] + "...")

                        audio_bytes = tts_audio_base64(text_to_speak, target_lang=user_lang)
                        st.session_state["fert_last_audio"] = audio_bytes

                    st.success("Audio ready ✅")

                except Exception as e:
                    st.error(f"TTS Error: {str(e)}")

        with colB:
            if st.session_state.get("fert_last_audio"):
                st.audio(st.session_state["fert_last_audio"], format="audio/wav")
            else:
                st.caption("Click 'Hear Explanation' to generate audio.")
    else:
        st.info("Generate a recommendation first — then you can listen to the AI explanation.")

