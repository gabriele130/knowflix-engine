from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from knowflix_engine.guardrails.evidence import evidence_guardrail
from knowflix_engine.llms import LLM_MAIN, LLM_CHEAP
from knowflix_engine.schemas.models import (
    ExtractedSkills,
    ReviewDraft,
    SummaryOutput,
)


@CrewBase
class ScoutCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def analyst(self) -> Agent:
        return Agent(config=self.agents_config["analyst"], llm=LLM_MAIN)

    @agent
    def tech_scout(self) -> Agent:
        return Agent(config=self.agents_config["tech_scout"], llm=LLM_MAIN)

    @agent
    def reviewer(self) -> Agent:
        return Agent(config=self.agents_config["reviewer"], llm=LLM_CHEAP)

    @task
    def summarize_company(self) -> Task:
        return Task(
            config=self.tasks_config["summarize_company"],
            output_pydantic=SummaryOutput,
        )

    @task
    def extract_company_skills(self) -> Task:
        return Task(
            config=self.tasks_config["extract_company_skills"],
            output_pydantic=ExtractedSkills,
            context=[],
            guardrail=evidence_guardrail,
            guardrail_max_retries=2,
        )

    @task
    def review_company(self) -> Task:
        return Task(
            config=self.tasks_config["review_company"],
            output_pydantic=ReviewDraft,
            context=[self.summarize_company(), self.extract_company_skills()],
            guardrail=evidence_guardrail,
            guardrail_max_retries=2,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
