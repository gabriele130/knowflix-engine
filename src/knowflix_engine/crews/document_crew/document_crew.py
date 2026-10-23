from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from knowflix_engine.guardrails.evidence import (
    GUARDRAIL_MAX_RETRIES,
    make_evidence_guardrail,
)
from knowflix_engine.llms import LLM_MAIN, LLM_CHEAP
from knowflix_engine.schemas.models import (
    ExtractedSkills,
    ReviewDraft,
    SummaryOutput,
)


@CrewBase
class DocumentCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def analyst(self) -> Agent:
        return Agent(config=self.agents_config["analyst"], llm=LLM_MAIN)

    @agent
    def skill_extractor(self) -> Agent:
        return Agent(config=self.agents_config["skill_extractor"], llm=LLM_MAIN)

    @agent
    def reviewer(self) -> Agent:
        return Agent(config=self.agents_config["reviewer"], llm=LLM_CHEAP)

    @task
    def summarize(self) -> Task:
        return Task(
            config=self.tasks_config["summarize"],
            output_pydantic=SummaryOutput,
        )

    @task
    def extract_skills(self) -> Task:
        return Task(
            config=self.tasks_config["extract_skills"],
            output_pydantic=ExtractedSkills,
            context=[],
            guardrail=make_evidence_guardrail("extract_skills"),
            guardrail_max_retries=GUARDRAIL_MAX_RETRIES,
        )

    @task
    def review(self) -> Task:
        return Task(
            config=self.tasks_config["review"],
            output_pydantic=ReviewDraft,
            context=[self.summarize(), self.extract_skills()],
            guardrail=make_evidence_guardrail("review"),
            guardrail_max_retries=GUARDRAIL_MAX_RETRIES,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )