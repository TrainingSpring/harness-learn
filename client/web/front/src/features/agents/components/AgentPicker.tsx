import type { AgentSummary } from "../../../api/types";
import { AgentPickerItem } from "./AgentPickerItem";

/** 新会话角色选择列表；单选结果由页面持有。 */
export function AgentPicker({ agents, selectedId, onSelect }: { agents: AgentSummary[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="agent-picker" role="list" aria-label="选择角色">
      {agents.map((agent) => (
        <AgentPickerItem key={agent.id} agent={agent} selected={agent.id === selectedId} onSelect={() => onSelect(agent.id)} />
      ))}
    </div>
  );
}
