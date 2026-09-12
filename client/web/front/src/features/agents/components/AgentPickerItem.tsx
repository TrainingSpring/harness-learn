import { Check } from "lucide-react";
import type { AgentSummary } from "../../../api/types";

/** 新对话页使用的紧凑角色选项。 */
export function AgentPickerItem({ agent, selected, onSelect }: { agent: AgentSummary; selected: boolean; onSelect: () => void }) {
  return (
    <button className={`agent-option ${selected ? "agent-option--selected" : ""}`} aria-pressed={selected} onClick={onSelect}>
      <span className="avatar" aria-hidden="true">{agent.name.slice(0, 1)}</span>
      <span className="agent-option__content">
        <strong>{agent.name}</strong>
        <span>{agent.description}</span>
        <span className="agent-option__meta">{agent.personality}{agent.expertise.length ? ` · ${agent.expertise.join(" / ")}` : ""}</span>
      </span>
      <span className="agent-option__check" aria-hidden="true">{selected && <Check size={16} />}</span>
    </button>
  );
}
