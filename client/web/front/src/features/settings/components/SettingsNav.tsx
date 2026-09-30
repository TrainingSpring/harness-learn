import { Bot, BookOpen, Server, SlidersHorizontal, Wrench } from "lucide-react";
import { NavLink } from "react-router-dom";

/** 设置模块的局部导航。 */
export function SettingsNav() {
  return (
    <nav className="settings-nav" aria-label="设置分类">
      <NavLink to="/settings/basic"><SlidersHorizontal size={16} />基础</NavLink>
      <NavLink to="/settings/llms"><Bot size={16} />LLM</NavLink>
      <NavLink to="/settings/tools"><Wrench size={16} />工具</NavLink>
      <NavLink to="/settings/skills"><BookOpen size={16} />Skills</NavLink>
      <NavLink to="/settings/mcp"><Server size={16} />MCP</NavLink>
    </nav>
  );
}
