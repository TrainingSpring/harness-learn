import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import type { McpServerSummary } from "../../../api/types";

interface McpServerPickerDialogProps {
  isOpen: boolean;
  servers: McpServerSummary[];
  selectedServerIds: string[];
  onClose: () => void;
  onConfirm: (serverIds: string[]) => void;
}

/** 在独立弹窗中选择 Agent 可使用的 MCP Server，不暴露 Server 内部 Tool 分配。 */
export function McpServerPickerDialog({ isOpen, servers, selectedServerIds, onClose, onConfirm }: McpServerPickerDialogProps) {
  const dialogRef = useModalFocus<HTMLDivElement>(isOpen);
  const [draftIds, setDraftIds] = useState<string[]>(selectedServerIds);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (isOpen) {
      setDraftIds(selectedServerIds);
      setQuery("");
    }
  }, [isOpen, selectedServerIds]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const filtered = useMemo(() => {
    const text = query.trim().toLocaleLowerCase();
    return text ? servers.filter((server) => `${server.name} ${server.description}`.toLocaleLowerCase().includes(text)) : servers;
  }, [query, servers]);

  if (!isOpen) return null;
  const toggle = (id: string) => setDraftIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  return <div className="dialog-backdrop skill-picker-backdrop">
    <div ref={dialogRef} className="permission-dialog skill-picker-dialog" role="dialog" aria-modal="true" aria-labelledby="mcp-picker-title" tabIndex={-1}>
      <div className="dialog-heading"><div><p className="eyebrow">角色配置</p><h2 id="mcp-picker-title">选择 MCP 服务</h2></div><Button variant="ghost" aria-label="关闭 MCP 选择" icon={<X size={17} />} onClick={onClose} /></div>
      <div className="skill-picker-toolbar"><label className="skill-picker-search"><Search size={16} aria-hidden="true" /><input aria-label="搜索 MCP 服务" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称或描述" autoFocus /></label><span className="skill-picker-count">已选择 {draftIds.length} 个</span></div>
      <div className="skill-picker-list" role="group" aria-label="MCP 服务列表">
        {filtered.length === 0 && <p className="form-hint">没有可用的 MCP 服务。</p>}
        {filtered.map((server) => <label className="skill-picker-option" key={server.id}>
          <input aria-label={server.name} type="checkbox" checked={draftIds.includes(server.id)} disabled={!server.enabled} onChange={() => toggle(server.id)} />
          <span className="skill-picker-option__content"><strong>{server.name}</strong><small>{server.description || (server.isLocal ? "本地 stdio" : "远程 Streamable HTTP")}</small></span>
          <span className={`status ${server.enabled ? "status--ok" : "status--muted"}`}>{server.enabled ? (server.isLocal ? "本地" : "远程") : "已禁用"}</span>
        </label>)}
      </div>
      <div className="dialog-actions"><Button type="button" onClick={onClose}>取消</Button><Button type="button" variant="primary" onClick={() => { onConfirm(draftIds); onClose(); }}>确认选择</Button></div>
    </div>
  </div>;
}
