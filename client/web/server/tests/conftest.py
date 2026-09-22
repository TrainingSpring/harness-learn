"""Web API 测试的隔离应用和持久化数据夹具。"""

from collections.abc import Iterator
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
AGENT_SOURCE = REPOSITORY_ROOT / "code" / "agent"
SERVER_SOURCE = Path(__file__).resolve().parents[1]
for source_path in (SERVER_SOURCE, REPOSITORY_ROOT, AGENT_SOURCE):
    if str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))

from app.config import WebServerSettings
from app.main import create_app
from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.llm_profile import LLMProfileRepository
from storage.types import AgentProfile, LLMProfile


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """创建绑定临时 workspace 的 API 客户端，并预置可查询配置。"""
    database = StateDatabase(str(tmp_path))
    database.initialize()
    try:
        LLMProfileRepository(database).save(
            LLMProfile(
                id="llm_TESTLLM001",
                name="本地 GPT",
                provider="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-5",
                api_key="sk-test-key",
                options={"temperature": 0.2},
            )
        )
        agents = AgentProfileRepository(database)
        agents.save(
            AgentProfile(
                id="agent_ENABLED001",
                name="工程师",
                description="负责实现和审查代码",
                personality="直接、严谨",
                expertise=["Python", "API"],
                llm_profile_id="llm_TESTLLM001",
                tools=["read", "bash"],
            )
        )
        agents.save(
            AgentProfile(
                id="agent_DISABLED01",
                name="停用角色",
                description="不可用于新会话",
                personality="",
                expertise=["Archive"],
                llm_profile_id="llm_TESTLLM001",
                tools=[],
                is_enabled=False,
            )
        )
    finally:
        database.close()

    app = create_app(WebServerSettings(workspace=tmp_path))
    with TestClient(app) as test_client:
        yield test_client
