# 🌾 KishanMitra AI (किसानमित्र AI)
## AI-Powered Smart Farming Assistant

KishanMitra AI is a multilingual, voice + text-based agricultural assistant designed to support farmers with real-time, data-driven insights.

It helps farmers make better decisions related to:
- Crops
- Irrigation
- Fertilizers
- Pests & Diseases
- Market Prices
- Government Schemes

The platform aims to bridge the digital divide in rural India by providing simple, accessible, and intelligent farming guidance in regional languages.

---

# 📌 About

KishanMitra AI uses a Retrieval-Augmented Generation (RAG) architecture to ensure responses are:
- Accurate  
- Context-aware  
- Data-grounded  

---

# ⚙️ Workflow

1. Input  
   - Voice or text query from the Streamlit interface  

2. Speech-to-Text (STT)  
   - Converts farmer voice into text  

3. Translation  
   - Sarvam AI translates regional language → English  

4. Processing Layer  
   - CSV-based engines (irrigation, fertilizer, etc.)  
   - RAG pipeline using LangChain + ChromaDB  
   - Web fallback (Google/Serper) for real-time data  

5. LLM Processing  
   - Gemini (prototype) generates contextual responses  

6. Output  
   - Translated response  
   - Optional voice output (TTS)  

---

# 🚀 Key Features

- 🎤 Voice + Text Query Support (Hindi + regional languages)  
- 🌾 AI Farm Advisor (weather, mandi prices, crop advice)  
- 💧 Irrigation Advisor (drip & sprinkler recommendations)  
- 🧪 Fertilizer Recommendation System (AI explanation + live data)  
- 🐛 Pest Information Assistant  
- 🌿 Crop Doctor (Disease detection via image upload)  
- 🏛️ Government Scheme Finder (verified schemes & subsidies)  
- 🌍 Multilingual Support using Sarvam AI  
- 🔎 RAG-Based Responses using datasets + real-time fallback  

---

# 🛠️ Installation & Setup

### Step 1: Clone Repository
```bash
git clone https://github.com/vardhman916/KishanMitra-AI
cd KishanMitra-AI
```

### Step 2: Create Virtual Environment
```bash
conda create -n kishanmitra python=3.10
conda activate kishanmitra
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Run the Application
```bash
streamlit run app.py
```

---

# 🔐 Environment Variables

Create a `.env` file and add:

```
OPENWEATHER_API_KEY=
GOOGLE_API_KEY=
MANDI_PROVIDER=
MANDI_DEBUG=
SERPER_API_KEY=
HYPERBROWSER_API_KEY=
BROWSE_CACHE_TTL_SEC=
BROWSE_MAX_SOURCES=
GEMINI_API_KEY=
KINDWISE_API_KEY=
KINDWISE_PRODUCT=crop.health
SARVAM_API_KEY=
```

---

# 💡 Sample Queries

- What should I grow in Rajasthan this season?  
- गेहूं की फसल के लिए कितना पानी चाहिए?  
- What is the cost of drip irrigation for 2 hectare?  
- Show government schemes for farmers in Rajasthan  
- What disease is affecting my crop? (upload image)  

---

# ⚠️ Known Limitations

- ⏳ Response delay due to free-tier APIs (Gemini Flash)  
- 🌾 Limited dataset coverage for some crops/regions  
- 🐛 Pest/disease detection optimized for specific crops (e.g., wheat, tomato)  
- 🌐 Requires internet connectivity for full functionality  

---

# 🔮 Future Scope

- ⚡ Faster response with production-level APIs  
- 🌾 Expanded crop & region-specific datasets  
- 🎙️ Full voice-based interaction system  
- 📡 Offline support for low-connectivity areas  
- 🌐 Integration with IoT sensors & real-time farm data  

---

# 📊 Conclusion

KishanMitra AI aims to become a complete digital farming assistant, enabling farmers to:

- Improve productivity  
- Reduce costs  
- Make smarter decisions  

by leveraging AI + real-time data insights 🌱
