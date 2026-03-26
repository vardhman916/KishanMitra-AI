import os
from pathlib import Path
import yaml
from dotenv import load_dotenv
from typing import Type

# ✅ CREWAI IMPORTS
from crewai import Agent, Task, Crew, Process
from crewai.project import CrewBase, agent, task, crew
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# ✅ CUSTOM TOOL IMPORT
from SRC.tools.disease_tool import DiseaseInfoTool

# ---------------- ROBUST PATH CONFIG ----------------
current_dir = Path(__file__).resolve().parent
project_root = current_dir
while not (project_root / ".env").exists():
    if project_root == project_root.parent:
        project_root = Path.cwd()
        break
    project_root = project_root.parent

load_dotenv(project_root / ".env")

# Load Configs
agents_config_path = project_root / "config" / "agents.yaml"
tasks_config_path = project_root / "config" / "tasks.yaml"

with open(agents_config_path, "r", encoding="utf-8") as f:
    AGENTS_CONFIG = yaml.safe_load(f) or {}

with open(tasks_config_path, "r", encoding="utf-8") as f:
    TASKS_CONFIG = yaml.safe_load(f) or {}

# ---------------- LLM ----------------
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash",
    temperature=0.1,
    google_api_key=os.getenv("GEMINI_API_KEY3"),
    max_tokens=200,
    request_timeout=40,
    max_retries=1,
    streaming=False
)

# ---------------- TOOL INPUT SCHEMA ----------------
class DiseaseInput(BaseModel):
    crop: str = Field(..., description="The crop name, e.g., 'Wheat'.")
    disease: str = Field(..., description="The disease name, e.g., 'Stinking Smut' or 'Yellow Rust'.")

# ---------------- TOOL WRAPPER ----------------
class DiseaseCrewTool(BaseTool):
    name: str = "disease_info_tool"
    description: str = (
        "Look up disease symptoms and control measures from the database. "
        "Requires 'crop' and 'disease' as inputs."
    )
    args_schema: Type[BaseModel] = DiseaseInput

    def _run(self, crop: str, disease: str) -> str:
        # Instantiate your original tool
        tool_instance = DiseaseInfoTool()
        inputs = {
            "crop": crop,
            "disease": disease
        }
        return tool_instance.run(inputs)

# Instantiate
disease_tool_instance = DiseaseCrewTool()

# ================= CREW =================
@CrewBase
class DiseaseDetectionCrew:
    """Disease Detection Crew"""
    
    agent_config = AGENTS_CONFIG
    task_config = TASKS_CONFIG

    @agent
    def disease_analyst(self) -> Agent:
        return Agent(
            config=self.agent_config.get('disease_analyst', {}),
            llm=llm,
            tools=[disease_tool_instance],
            verbose=True,
            allow_delegation=False,
            max_iter=1,
            max_execution_time=30
        )

    @task
    def disease_detection_task(self) -> Task:
        return Task(
            config=self.task_config.get('disease_detection_task', {}),
            agent=self.disease_analyst()
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[self.disease_analyst()],
            tasks=[self.disease_detection_task()],
            process=Process.sequential,
            verbose=True,
            max_rpm=10
        )
