import streamlit as st
import json
from SRC.tools.Pest_info_tool import PestInfoTool
from SRC.agents.pest_agent import generate_pest_summary
from SRC.sarvam_translate import translate_text


def render_pest_tab():

    st.header("🐛 Pest Information Tool")
    with st.expander("ℹ️ About This Pest Information Tool"):
        st.markdown("""
            ### English

            This Pest Information Tool helps farmers and agriculture students understand major pests affecting selected crops. 
            You can currently select Wheat, Mustard, and Tomato crops and explore common pests related to them. 
            For Wheat, pests such as Aphids, Termites, Army worm, Pink stem borer, and different nematodes are available. 
            For Mustard, you can check Bihar hairy caterpillar, Mustard aphid, Painted bug, Diamondback moth and others. 
            For Tomato, pests like Whitefly, Tobacco caterpillar, Gram pod borer, Root-knot nematode and Spider mites are supported. 

            This tab is designed to provide pest details, symptoms, impact on crops, and management guidance in simple language. 
            It also allows you to translate the explanation into multiple Indian languages to make the information accessible to farmers in their regional language.

            ---

            ### हिंदी

            यह Pest Information Tool किसानों और कृषि छात्रों को चुनी गई फसलों में लगने वाले प्रमुख कीटों को समझने में सहायता करता है। 
            वर्तमान में आप गेहूं, सरसों और टमाटर फसल का चयन कर सकते हैं और उनसे संबंधित सामान्य कीटों की जानकारी प्राप्त कर सकते हैं। 
            गेहूं के लिए माहू (Aphids), दीमक (Termites), कटवर्म / आर्मी वर्म, गुलाबी तना छेदक (Pink stem borer) तथा विभिन्न प्रकार के सूत्रकृमि (Nematodes) उपलब्ध हैं। 
            सरसों के लिए बिहार हेयरी कैटरपिलर (रोयेदार इल्ली), सरसों माहू, पेंटेड बग (रंगा कीट), डायमंडबैक मॉथ और अन्य प्रमुख कीट शामिल हैं। 
            टमाटर के लिए सफेद मक्खी (Whitefly), तंबाकू की इल्ली, चना फली छेदक (Gram pod borer), जड़ गांठ सूत्रकृमि (Root-knot nematode) और मकड़ी कीट (Spider mites) जैसे कीट उपलब्ध हैं।

            इस टैब का उद्देश्य कीटों की पहचान, उनके लक्षण, फसल पर प्रभाव और नियंत्रण उपायों की जानकारी सरल भाषा में प्रदान करना है। 
            साथ ही, आप जानकारी को विभिन्न भारतीय भाषाओं में अनुवाद भी कर सकते हैं ताकि किसान अपनी क्षेत्रीय भाषा में इसे आसानी से समझ सकें।
            """)

    # ---------------- LOAD PEST TOOL ----------------
    try:
        pest_tool = PestInfoTool("data/Pest Data.xlsx")
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    # ---------------- LOAD CONFIG JSON ----------------
    try:
        with open("data/crop_pest_config.json", "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        st.error("crop_pest_config.json file not found inside data folder.")
        return

    # ---------------- SESSION STATE ----------------
    if "pest_data" not in st.session_state:
        st.session_state.pest_data = None

    if "summary" not in st.session_state:
        st.session_state.summary = None

    if "translated_text" not in st.session_state:
        st.session_state.translated_text = None

    # ---------------- CROP SELECTION ----------------
    crop_input = st.selectbox(
        "Select Crop",
        config.get("crop_list", [])
    )

    # ---------------- PEST SELECTION ----------------
    pest_input = st.selectbox(
        "Select Pest",
        config.get("pest_by_crop", {}).get(crop_input, [])
    )

    # ---------------- FETCH PEST INFO ----------------
    if st.button("Get Pest Information"):

        pest_data = pest_tool.get_pest_info(crop_input, pest_input)

        if pest_data is None:
            st.error("No pest information found.")
        else:
            summary = generate_pest_summary(pest_data)

            st.session_state.pest_data = pest_data
            st.session_state.summary = summary
            st.session_state.translated_text = None  # reset old translation

    # ---------------- DISPLAY CONTENT ----------------
    if st.session_state.pest_data:

        if st.session_state.pest_data.get("image"):
            st.image(st.session_state.pest_data["image"])
        else:
            st.info("No image available for this pest in the dataset.")

        st.subheader("🇬🇧 English Explanation")
        st.markdown(st.session_state.summary)

        # ---------------- TRANSLATION SECTION ----------------
        st.subheader("🌍 Translate")

        language_options = {
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
            "Assamese": "as-IN",
        }

        selected_language = st.selectbox(
            "Choose Language",
            list(language_options.keys())
        )

        if st.button("Translate"):
            with st.spinner("Translating..."):
                translated_text = translate_text(
                    st.session_state.summary,
                    language_options[selected_language]
                )
                st.session_state.translated_text = translated_text

        # ---------------- SHOW TRANSLATED CONTENT ----------------
        if st.session_state.translated_text:
            st.subheader("🌐 Translated Content")

            if str(st.session_state.translated_text).startswith("Translation"):
                st.error(st.session_state.translated_text)
            else:
                st.markdown(st.session_state.translated_text)