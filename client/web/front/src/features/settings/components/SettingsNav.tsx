import { Bot, Palette, Wrench } from "lucide-react";
import { NavLink } from "react-router-dom";

/** 设置模块的局部导航。 */
export function SettingsNav() {
  return (
    <nav className="settings-nav" aria-label="设置分类">
      <NavLink to="/settings/appearance"><Palette size={16} />外观</NavLink>
      <NavLink to="/settings/llms"><Bot size={16} />LLM</NavLink>
      <NavLink to="/settings/tools"><Wrench size={16} />工具</NavLink>
    </nav>
  );
}
