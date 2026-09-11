"""受信任工具模块的发现与加载。"""

import importlib
import pkgutil
import re
from dataclasses import dataclass
from types import ModuleType

from .types import Tool


@dataclass(frozen=True)
class ToolMetadata:
    """工具供选择和展示的静态元数据。"""

    name: str
    schema: dict
    permission: object


class ToolCatalog:
    """从 tools 包中的受信任模块加载 Tool 定义。

    数据库或用户配置只能提供工具名称，不能提供 Python 模块路径和函数路径。
    Catalog 将名称映射到 tools.<name>.REGISTER，并验证 REGISTER 与 schema 名称
    一致，从而把动态加载边界集中在一个位置。
    """

    _NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def get(self, name: str) -> Tool:
        """按工具名称加载并校验一个 Tool。

        Args:
            name: 工具模块名，例如 read 或 bash。

        Returns:
            代码模块导出的有效 Tool 对象。

        Raises:
            ValueError: 名称非法、模块不存在、REGISTER 缺失或名称不一致时抛出。
        """
        self._validate_name(name)
        module_name = f"tools.{name}"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name == module_name:
                raise ValueError(f"工具不存在: {name}") from error
            raise

        return self._tool_from_module(name, module)

    def list_available(self) -> list[ToolMetadata]:
        """发现 tools 包中所有有效的 REGISTER，并按名称排序。"""
        import tools

        metadata: list[ToolMetadata] = []
        for module_info in pkgutil.iter_modules(tools.__path__):
            try:
                tool = self.get(module_info.name)
            except ValueError:
                # types、tools、catalog 等辅助模块不是工具定义，应跳过。
                continue
            metadata.append(
                ToolMetadata(
                    name=module_info.name,
                    schema=tool.schema,
                    permission=tool.permission,
                )
            )
        return sorted(metadata, key=lambda item: item.name)

    def validate_names(self, names: list[str]) -> None:
        """验证一组工具名称都能映射到有效的代码工具。"""
        for name in names:
            self.get(name)

    @classmethod
    def _validate_name(cls, name: str) -> None:
        """拒绝可能突破 tools 包边界的模块名称。"""
        if not isinstance(name, str) or cls._NAME_PATTERN.fullmatch(name) is None:
            raise ValueError(f"非法的工具名称: {name}")

    @staticmethod
    def _tool_from_module(name: str, module: ModuleType) -> Tool:
        """校验工具模块导出的 REGISTER。"""
        tool = getattr(module, "REGISTER", None)
        if not isinstance(tool, Tool):
            raise ValueError(f"{name}.REGISTER 不是有效的 Tool")
        if tool.schema.get("name") != name:
            raise ValueError(
                f"工具名称不一致: 配置名={name}, schema名称={tool.schema.get('name')}"
            )
        return tool
