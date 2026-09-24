import { useState } from "react";
import { Check, Folder, LoaderCircle, X } from "lucide-react";
import type { AgentSummary } from "../../../api/types";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import { AgentPicker } from "../../agents/components/AgentPicker";
import { ProjectPicker } from "./ProjectPicker";

interface NewSessionDialogProps {
  agents: AgentSummary[];
  selectedAgentId: string | null;
  workspacePath: string | null;
  isSubmitting: boolean;
  error: string | null;
  onAgentSelect: (agentId: string) => void;
  onWorkspaceChange: (path: string | null) => void;
  onConfirm: () => void;
  onClose: () => void;
}

/** 新建 Session 的确认弹窗：角色必选，工作目录可选。 */
export function NewSessionDialog({ agents, selectedAgentId, workspacePath, isSubmitting, error, onAgentSelect, onWorkspaceChange, onConfirm, onClose }: NewSessionDialogProps) {
  const [showWorkspacePicker, setShowWorkspacePicker] = useState(false);
  const dialog = useModalFocus<HTMLDivElement>();
  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId) ?? null;

  return (
    <>
      <div className="dialog-backdrop">
        <div ref={dialog} className="permission-dialog new-session-dialog" role="dialog" aria-modal="true" aria-labelledby="new-session-title" tabIndex={-1}>
          <div className="dialog-heading">
            <div><p className="eyebrow">会话设置</p><h2 id="new-session-title">新建对话</h2></div>
            <Button variant="ghost" aria-label="取消新建对话" icon={<X size={17} />} onClick={onClose} disabled={isSubmitting} />
          </div>
          <div className="new-session-dialog__section">
            <div className="new-session-dialog__section-heading">
              <div><h3>选择角色</h3><p>角色是必选项。</p></div>
              {selectedAgent && <span className="new-session-dialog__selected">已选择：{selectedAgent.name}</span>}
            </div>
            <AgentPicker agents={agents} selectedId={selectedAgentId} onSelect={onAgentSelect} />
          </div>
          <div className="new-session-dialog__section">
            <div className="new-session-dialog__section-heading"><div><h3>工作目录</h3><p>可选。未选择时仍可进行普通对话。</p></div></div>
            <button type="button" className="new-session-dialog__workspace" onClick={() => setShowWorkspacePicker(true)} disabled={isSubmitting}>
              <Folder size={16} aria-hidden="true" /><span>{workspacePath ?? "不选择工作目录"}</span>
            </button>
          </div>
          {error && <p className="inline-error" role="alert">{error}</p>}
          <div className="permission-dialog__actions new-session-dialog__actions">
            <Button type="button" onClick={onClose} disabled={isSubmitting}>取消</Button>
            <Button type="button" variant="primary" icon={isSubmitting ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} disabled={!selectedAgent || isSubmitting} onClick={onConfirm}>{isSubmitting ? "正在创建" : "确认创建"}</Button>
          </div>
        </div>
      </div>
      {showWorkspacePicker && <ProjectPicker selectedPath={workspacePath} onSelect={onWorkspaceChange} onClose={() => setShowWorkspacePicker(false)} />}
    </>
  );
}
