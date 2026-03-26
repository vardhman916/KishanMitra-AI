import os
import signal
import threading

# Disable telemetry/instrumentation before importing tabs that may load CrewAI.
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

# Streamlit runs app code on a worker thread; some SDKs incorrectly call signal.signal there.
_original_signal = signal.signal


def _safe_signal(sig, handler):
    if threading.current_thread() is not threading.main_thread():
        return None
    return _original_signal(sig, handler)


signal.signal = _safe_signal

import streamlit as st

st.set_page_config(page_title="Kishan Mitra AI", layout="wide")

st.sidebar.title("Kishan Mitra AI")
page = st.sidebar.radio(
    "Go to",
    [
        "AI Farm Advisor",
        "Scheme Finder",
        "Crop Doctor",
        "Fertilizer",
        "Pest Information",
        "Irrigation"
    ],
)

if page == "AI Farm Advisor":
    from SRC.tabs import advisor_tab

    advisor_tab.render()
elif page == "Scheme Finder":
    from SRC.tabs import scheme_tab

    scheme_tab.render()
elif page == "Crop Doctor":
    from SRC.tabs import disease_tab

    disease_tab.render()
elif page == "Fertilizer":
    from SRC.tabs import fert_calc_tab_v1

    fert_calc_tab_v1.render()
elif page == "Pest Information":
    from SRC.tabs import pest_tabs

    pest_tabs.render_pest_tab()
elif page == "Irrigation":
    from SRC.tabs import irrigation_tab

    irrigation_tab.show_fertilizer_tab()

