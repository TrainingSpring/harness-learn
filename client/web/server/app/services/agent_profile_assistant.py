"""使用已保存的 LLM 配置生成 Agent 角色草案。"""

import json
from collections.abc import Callable
from typing import Any

from head.llm import LLM
from pydantic import ValidationError
from storage.repositories.llm_profile import LLMProfileRepository

from ..schemas.agent import AgentProfileSuggestion


class LLMProfileNotFoundError(Exception):
    """请求引用的 LLMProfile 不存在。"""


class InvalidAgentSuggestionError(Exception):
    """模型输出不是约定的角色草案 JSON。"""


LLMFactory = Callable[[str, str, str, str], Any]


class AgentProfileAssistant:
    """根据用户描述和指定 LLM 配置生成结构化角色草案。

    Attributes:
        llm_profiles: 用于读取所选模型、地址和 API Key 的仓储。
        llm_factory: 创建 LLM 调用对象的工厂，允许测试替换外部模型。

    模型输出属于不受信任输入，必须经过 JSON 解析和 Pydantic 字段约束，
    不能直接返回给浏览器或写入 AgentProfile。
    """

    _SYSTEM_PROMPT = """你负责根据用户给出的角色用途描述生成 Agent 角色配置。
只返回一个 JSON 对象，不要返回 Markdown、代码块或解释文字。
JSON 必须且只能包含以下字段：
- name: 简洁的中文角色名称
- description: 清晰完整的角色职责描述
- personality: 角色的表达风格和行为特点
- expertise: 字符串数组，列出角色擅长领域
不要生成工具、权限、模型配置或任何密钥相关内容。"""

    def __init__(
        self,
        llm_profiles: LLMProfileRepository,
        *,
        llm_factory: LLMFactory = LLM,
    ) -> None:
        """创建角色草案生成服务。

        Args:
            llm_profiles: 已初始化的 LLMProfile 仓储。
            llm_factory: LLM 对象工厂，主要用于隔离单元测试外部请求。
        """
        self.llm_profiles = llm_profiles
        self.llm_factory = llm_factory

    def suggest(self, description: str, llm_profile_id: str) -> dict[str, Any]:
        """调用所选模型生成并验证角色草案。

        Args:
            description: 用户填写的原始角色用途描述。
            llm_profile_id: 用户在表单中选择的 LLMProfile ID。

        Returns:
            只包含 name、description、personality、expertise 的字典。

        Raises:
            LLMProfileNotFoundError: LLMProfile 不存在或 ID 非法。
            InvalidAgentSuggestionError: 模型没有返回符合契约的 JSON。
            Exception: 模型客户端调用失败时保留原异常供 API 边界转换。
        """
        try:
            profile = self.llm_profiles.get(llm_profile_id)
        except ValueError as error:
            raise LLMProfileNotFoundError(llm_profile_id) from error
        if profile is None:
            raise LLMProfileNotFoundError(llm_profile_id)

        if not profile.api_key:
            raise ValueError(f"LLM 配置未设置 API Key: {profile.id}")
        llm = self.llm_factory(
            profile.base_url or "",
            profile.api_key,
            profile.model,
            self._SYSTEM_PROMPT,
        )
        response = llm.call_responses(
            f"请根据下面的原始描述生成角色配置：\n\n{description.strip()}"
        )
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise InvalidAgentSuggestionError("模型未返回文本")

        try:
            payload = json.loads(output_text)
            suggestion = AgentProfileSuggestion.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as error:
            raise InvalidAgentSuggestionError("模型返回格式无效") from error
        return suggestion.model_dump()
