import os
from crewai import LLM

_MODEL = os.getenv("MODEL", "gemini/gemini-3.6-flash")

LLM_MAIN = LLM(model=_MODEL, temperature=0.2)
LLM_CHEAP = LLM(model=_MODEL, temperature=0.0)