import streamlit as st
import os
import time
from typing import Type
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from SRC.voice_utils import tts_audio_base64

# CrewAI Imports
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import BaseTool

# ✅ IMPORT YOUR EXISTING TOOLS
# Ensure these files exist in SRC/tools/ as per your previous setup
from SRC.tools.disease_detection_tool import DiseaseDetectionTool
from SRC.tools.disease_tool import DiseaseInfoTool
from SRC.voice_utils import from_english

# --- SETUP ---
load_dotenv()

# --- 1. TOOL WRAPPERS (Adapting your tools for CrewAI) ---

class ImageScanInput(BaseModel):
    image_path: str = Field(..., description="Full path to the image file.")

class ImageScanTool(BaseTool):
    name: str = "Crop Health Scanner"
    description: str = "Analyzes a crop image file path to detect diseases and returns the Top Disease Name."
    args_schema: Type[BaseModel] = ImageScanInput

    def _run(self, image_path: str) -> str:
        tool = DiseaseDetectionTool()
        return str(tool.analyze_crop(image_path))

class DBInput(BaseModel):
    crop: str = Field(..., description="Crop name (e.g. Wheat)")
    disease: str = Field(..., description="Disease name (e.g. Yellow Rust)")

class DBTool(BaseTool):
    name: str = "Disease Knowledge Base"
    description: str = "Look up official symptoms and chemical control for a specific disease."
    args_schema: Type[BaseModel] = DBInput

    def _run(self, crop: str, disease: str) -> str:
        tool = DiseaseInfoTool()
        return tool.run({"crop": crop, "disease": disease})

# --- 2. THE COMBINED AGENT & CREW (Defined Inline) ---

# ... (imports remain the same)

# --- 2. THE COMBINED AGENT & CREW ---

def run_disease_crew(image_path: str):
    """
    Runs the sequential diagnosis process: Scan -> Lookup -> Report
    """
    
    llm = LLM(
        model="gemini-2.5-flash", 
        api_key=os.getenv("GEMINI_API_KEY5"), 
        temperature=0.1
    )

    diagnostician = Agent(
        role="Lead Plant Pathologist",
        goal="Identify the disease from the image and find its treatment in the official database.",
        backstory=(
            "You are an expert in crop pathology. Your workflow is strictly sequential:\n"
            "1. Scan the image to find the raw disease name.\n"
            "2. Map that raw name to the OFFICIAL DATABASE KEYS provided in the task.\n"
            "3. Look up the OFFICIAL name in the 'Disease Knowledge Base'.\n"
            "4. Report the combined findings."
        ),
        llm=llm,
        tools=[ImageScanTool(), DBTool()],
        verbose=True,
        allow_delegation=False
    )

    # ✅ HERE IS THE FIX: We give the LLM the "Menu" of valid names.
    valid_diseases = """
    - Powdery Mildew
    - Loose Smut
    - Brown Rust
    - Stripe Rust / Yellow Rust
    - Black Rust
    - Flag Smut
    - Hill Bunt (Stinking Smut)
    - Karnal Bunt
    - Leaf Blight
    - Fusarium Leaf Blotch
    - Foot Rot
    - Head Scab
    - Helminthosporium Leaf Blotch (Spot Blotch)
    - Seedling Blight
    """

    diagnosis_task = Task(
        description=(
            f"1. The user has provided an image at: '{image_path}'.\n"
            "2. Use the 'Crop Health Scanner' tool to analyze this image.\n"
            "3. EXTRACT the raw disease name (e.g., 'Wheat Yellow Rust').\n"
            "4. **CRITICAL STEP:** Map the raw name to one of the **VALID DATABASE KEYS** below:\n"
            f"{valid_diseases}\n"
            "   - Example: If scan says 'Wheat Yellow Rust', map it to 'Stripe Rust / Yellow Rust'.\n"
            "   - Example: If scan says 'Spot Blotch', map it to 'Helminthosporium Leaf Blotch (Spot Blotch)'.\n"
            "5. If the plant is healthy, stop and report 'Healthy'.\n"
            "6. Use the 'Disease Knowledge Base' tool with:\n"
            "   - crop: 'Wheat' (Default)\n"
            "   - disease: The **EXACT MAPPED NAME** from the list above.\n"
            "7. Return the combined findings: Disease Name, Confidence, Confirmed Symptoms, and Chemical Control."
        ),
        expected_output=(
            "A final report containing:\n"
            "- Disease Name & Confidence\n"
            "- Symptoms (from Excel DB)\n"
            "- Control/Treatment (from Excel DB)"
        ),
        agent=diagnostician
    )

    crew = Crew(
        agents=[diagnostician],
        tasks=[diagnosis_task],
        process=Process.sequential,
        verbose=True
    )
    
    return crew.kickoff()

# --- 3. STREAMLIT UI ---

def save_uploaded_file(uploaded_file):
    """Saves uploaded file to disk and returns path."""
    IMG_DIR = "uploaded_images"
    os.makedirs(IMG_DIR, exist_ok=True)
    
    file_path = os.path.join(IMG_DIR, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path
              

def render():
    col1, col2 = st.columns([0.9, 0.1])
    with col1:
        st.title("🧬 Crop Doctor (Disease Detection)")
        st.markdown("Instantly identify crop diseases and get verified treatments.")
    
    with col2:
        with st.popover("ℹ️ Help"):
            st.markdown("""
            **How to use:**
            1. Upload or take a photo.
            2. Click Diagnose Crop.
            3. View English + Translated report.
            """)

    st.divider()

    # ✅ SESSION STORAGE
    if "disease_result_en" not in st.session_state:
        st.session_state["disease_result_en"] = ""
    if "disease_result_translated" not in st.session_state:
        st.session_state["disease_result_translated"] = ""
    if "disease_audio" not in st.session_state:
        st.session_state["disease_audio"] = None

    # ✅ Language selector
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

    selected_lang_name = st.selectbox("🌐 Select Response Language", list(SUPPORTED_LANGS.keys()))
    selected_lang_code = SUPPORTED_LANGS[selected_lang_name]

    # Image Input
    input_option = st.radio("Select Input Method:", ["📂 Upload Image", "📸 Camera"], horizontal=True)

    image_path = None

    if input_option == "📂 Upload Image":
        uploaded_file = st.file_uploader("Upload a leaf image", type=["jpg", "png", "jpeg"])
        if uploaded_file:
            image_path = save_uploaded_file(uploaded_file)
            st.image(image_path, caption="Uploaded Image", width=300)

    elif input_option == "📸 Camera":
        camera_file = st.camera_input("Take a picture")
        if camera_file:
            image_path = save_uploaded_file(camera_file)
            st.image(image_path, caption="Camera Image", width=300)

    # Diagnose Button
    if image_path:
        if st.button("🔍 Diagnose Crop", type="primary"):
            status = st.status("🔬 Analyzing...", expanded=True)

            try:
                status.write("📡 Scanning image for diseases...")

                result = run_disease_crew(image_path)

                status.update(label="✅ Diagnosis Complete", state="complete", expanded=False)

                # Store English result
                st.session_state["disease_result_en"] = str(result)

                # Translate if not English
                if selected_lang_code != "en-IN":
                    translated = from_english(str(result), selected_lang_code)
                else:
                    translated = str(result)

                st.session_state["disease_result_translated"] = translated

            except Exception as e:
                status.update(label="❌ Error", state="error")
                st.error(f"Analysis failed: {str(e)}")

    # ✅ Always display results if available
    if st.session_state["disease_result_en"]:

        st.divider()
        st.markdown("## 📋 Original Report (English)")
        st.markdown(st.session_state["disease_result_en"])

        if selected_lang_code != "en-IN":
            st.divider()
            st.markdown(f"## 🌐 Translated Report ({selected_lang_name})")
            st.markdown(st.session_state["disease_result_translated"])
    
    # ---------------- TTS SECTION ----------------
    st.divider()
    st.subheader("🔊 Listen to Report")

    if st.session_state["disease_result_en"]:

        col1, col2 = st.columns([0.3, 0.7])

        with col1:
            if st.button("🔊 Hear Report", use_container_width=True):
                try:
                    with st.spinner("Generating voice..."):

                        # Decide which text to speak
                        if selected_lang_code == "en-IN":
                            text_to_speak = st.session_state["disease_result_en"]
                        else:
                            text_to_speak = st.session_state["disease_result_translated"]

                        # Limit length (important for TTS APIs)
                        MAX_TTS_CHARS = 1200
                        if len(text_to_speak) > MAX_TTS_CHARS:
                            text_to_speak = text_to_speak[:MAX_TTS_CHARS] + "..."

                        audio_bytes = tts_audio_base64(
                            text_to_speak,
                            target_lang=selected_lang_code
                        )

                        st.session_state["disease_audio"] = audio_bytes

                    st.success("Audio ready ✅")

                except Exception as e:
                    st.error(f"TTS Error: {str(e)}")

        with col2:
            if st.session_state.get("disease_audio"):
                st.audio(st.session_state["disease_audio"], format="audio/wav")
            else:
                st.caption("Click 'Hear Report' to generate audio.")

    else:
        st.info("Run diagnosis first to enable voice output.")
