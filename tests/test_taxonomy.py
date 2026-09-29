import pytest
from knowflix_engine.taxonomy import link_profile

def test_link_profile_exact_match():
    profile = {"skills": [{"label": "Python", "confidence": 0.9}]}
    linked = link_profile(profile)
    assert linked["skills"][0]["skill_id"] == "tax-python"

def test_link_profile_synonym():
    profile = {"skills": [{"label": "Pandas", "confidence": 0.8}]}
    linked = link_profile(profile)
    # Assumiamo che "Pandas" si ricolleghi a "Data Analysis" o simile via sinonimo
    assert linked["skills"][0]["skill_id"] is not None

def test_link_profile_below_threshold():
    profile = {"skills": [{"label": "Cucinare la pasta", "confidence": 0.9}]}
    linked = link_profile(profile)
    # Se non c'è match, skill_id resta None
    assert linked["skills"][0]["skill_id"] is None
