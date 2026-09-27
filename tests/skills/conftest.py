import pytest

from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.llm_profile import LLMProfileRepository
from storage.types import AgentProfile, LLMProfile


@pytest.fixture
def database(tmp_path):
    database = StateDatabase(str(tmp_path))
    database.initialize()
    LLMProfileRepository(database).save(
        LLMProfile("llm_TESTLLM001", "Test", "responses", None, "model", "key")
    )
    AgentProfileRepository(database).save(
        AgentProfile("agent_TESTAGENT1", "Agent", "desc", "", [], "llm_TESTLLM001", [])
    )
    yield database
    database.close()
