from knowflix_engine.main import KnowflixFlow

flow = KnowflixFlow()
flow.kickoff(inputs={"job_id": "az001", "job_type": "company",
                     "company_raw": {"nome": "Acme Srl"}})
print(flow.state.profile, flow.state.warnings)