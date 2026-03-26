import time
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

from crewai import Agent, Task, Crew, Process,LLM
from langchain_google_genai import ChatGoogleGenerativeAI

# ✅ IMPORT TOOL CLASSES
from SRC.agents.weather_agent import WeatherCrewTool
from SRC.agents.market_price_agent import MarketCrewTool
from SRC.agents.disease_detection_agent import DiseaseCrewTool

# --- PATH & CONFIG ---
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
load_dotenv(project_root / ".env")

with open(project_root / "config" / "agents.yaml", "r", encoding="utf-8") as f:
    AGENTS_CONFIG = yaml.safe_load(f) or {}
with open(project_root / "config" / "tasks.yaml", "r", encoding="utf-8") as f:
    TASKS_CONFIG = yaml.safe_load(f) or {}

# --- 1. RESTRICTED LLM (Free Tier Safe) ---
llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash",
    temperature=0.1,
    google_api_key=os.getenv("GEMINI_API_KEY5"),
    max_tokens=1000,
    max_retries=1,      # Fail fast
    request_timeout=60, 
    streaming=False
)

class DynamicFarmSystem:
    
    def __init__(self):
        print("🔧 Initializing Tools...")
        self.weather_tool = WeatherCrewTool()
        self.market_tool = MarketCrewTool()
        self.disease_tool = DiseaseCrewTool()

    # --- 2. AGENT FACTORY (No Delegation) ---
    def _get_agent(self, key, tool=None):
        return Agent(
            config=AGENTS_CONFIG[key], 
            llm=llm, 
            tools=[tool] if tool else [], 
            verbose=True,
            allow_delegation=False,  # ⛔ CRITICAL: Saves API calls
            max_iter=1,              # ⛔ CRITICAL: One shot only
        )

    # --- 3. ZERO-COST PYTHON ROUTER ---
    def _detect_intent(self, query: str) -> dict:
        """Decides which tools to run using keywords (Cost: 0 Tokens)"""
        q = query.lower()
        plan = {"weather": False, "market": False, "disease": False}
        
        if any(w in q for w in ["weather", "rain", "forecast", "temp", "cloud"]):
            plan["weather"] = True
        if any(w in q for w in ["price", "mandi", "rate", "cost", "sell"]):
            plan["market"] = True
        if any(w in q for w in ["disease", "pest", "yellow", "rust", "treatment"]):
            plan["disease"] = True
            
        return plan

    # --- 4. THROTTLED EXECUTION LOOP ---
    def run(self, query: str):
        print(f"\n🧠 Analyzing Query: '{query}'")
        
        # Step A: Python Plan (Free)
        plan = self._detect_intent(query)
        print(f"📋 Execution Plan: {plan}")

        results = [] 
        
        # Helper to run a SINGLE task safely
        def run_single_task(agent_key, tool, task_key, label):
            print(f"\n🚀 Starting {label} Agent...")
            agent = self._get_agent(agent_key, tool)
            task = Task(config=TASKS_CONFIG[task_key], agent=agent)
            
            # Create a single-task crew
            crew = Crew(
                agents=[agent], 
                tasks=[task], 
                verbose=True,
                process=Process.sequential # ✅ STRICT SEQUENTIAL
            )
            return crew.kickoff(inputs={'query': query})

        # --- EXECUTE SEQUENTIALLY WITH FORCED SLEEP ---
        
        # 1. Weather
        if plan['weather']:
            try:
                out = run_single_task('weather_analyst', self.weather_tool, 'weather_task', "Weather")
                results.append(f"🌤️ WEATHER REPORT:\n{out}")
                print("⏳ Cooling down API (10s)...")
                time.sleep(20) # <--- PREVENTS 429 ERROR
            except Exception as e:
                print(f"⚠️ Weather Failed: {e}")

        # 2. Market
        if plan['market']:
            try:
                out = run_single_task('market_analyst', self.market_tool, 'market_price_task', "Market")
                results.append(f"💰 MARKET REPORT:\n{out}")
                print("⏳ Cooling down API (10s)...")
                time.sleep(20)
            except Exception as e:
                print(f"⚠️ Market Failed: {e}")

        # 3. Disease
        if plan['disease']:
            try:
                out = run_single_task('disease_analyst', self.disease_tool, 'disease_detection_task', "Disease")
                results.append(f"🚑 DISEASE REPORT:\n{out}")
                print("⏳ Cooling down API (10s)...")
                time.sleep(20)
            except Exception as e:
                print(f"⚠️ Disease Failed: {e}")

        # 4. Final Synthesis
        if not results:
            return "Please ask about Weather, Market Prices, or Diseases."

        print("\n🚜 Synthesizing Final Advisory...")
        advisor = self._get_agent('chief_advisor')
        
        combined_data = "\n\n".join(str(r) for r in results)
        
        synthesis_task = Task(
            description=f"""
            The user asked: "{query}"
            
            Here are the reports from your specialists:
            =========================================
            {combined_data}
            =========================================
            
            Combine these into a helpful final answer for the Indian farmer.
            Use ONLY the data provided above.
            """,
            expected_output="Final consolidated advisory.",
            agent=advisor
        )
        
        final_crew = Crew(agents=[advisor], tasks=[synthesis_task], verbose=True)
        return final_crew.kickoff()