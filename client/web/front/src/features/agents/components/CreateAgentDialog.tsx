import { useEffect, useState, type FormEvent } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import type { CreateAgentRequest, LLMProfileSummary, ToolSummary } from "../../../api/types";

interface CreateAgentDialogProps {
  isOpen: boolean;
  isSubmitting: boolean;
  error: string | null;
  llmProfiles: LLMProfileSummary[];
  tools: ToolSummary[];
  onClose: () => void;
  onSubmit: (request: CreateAgentRequest) => void;
}

/** 角色创建弹窗；负责收集表单值，不直接访问 API 或数据库。 */
export function CreateAgentDialog({
  isOpen,
  isSubmitting,
  error,
  llmProfiles,
  tools,
  onClose,
  onSubmit,
}: CreateAgentDialogProps) {
  const dialogRef = useModalFocus<HTMLDivElement>(isOpen);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [personality, setPersonality] = useState("");
  const [expertise, setExpertise] = useState("");
  const [llmProfileId, setLlmProfileId] = useState("");
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [permissionMode, setPermissionMode] = useState("BUILD");
  const [isEnabled, setIsEnabled] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setName("");
    setDescription("");
    setPersonality("");
    setExpertise("");
    setLlmProfileId("");
    setSelectedTools([]);
    setPermissionMode("BUILD");
    setIsEnabled(true);
    setFormError(null);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const toggleTool = (toolName: string) => {
    setSelectedTools((current) => current.includes(toolName)
      ? current.filter((item) => item !== toolName)
      : [...current, toolName]);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    if (!llmProfileId) {
      setFormError("请选择一个 LLM 配置");
      return;
    }
    onSubmit({
      name: name.trim(),
      description: description.trim(),
      personality: personality.trim(),
      expertise: expertise.split(",").map((item) => item.trim()).filter(Boolean),
      llmProfileId,
      tools: selectedTools,
      permissionMode,
      isEnabled,
    });
  };

  return (
    <div className="dialog-backdrop">
      <div
        ref={dialogRef}
        className="permission-dialog create-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-agent-title"
        tabIndex={-1}
      >
        <div className="dialog-heading">
          <div><p className="eyebrow">角色目录</p><h2 id="create-agent-title">新增角色</h2></div>
          <Button variant="ghost" aria-label="关闭" icon={<X size={17} />} onClick={onClose} />
        </div>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="form-field"><span>名称</span><input value={name} onChange={(event) => setName(event.target.value)} required autoFocus /></label>
          <label className="form-field"><span>描述</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} /></label>
          <label className="form-field"><span>性格</span><input value={personality} onChange={(event) => setPersonality(event.target.value)} /></label>
          <label className="form-field"><span>擅长领域</span><input value={expertise} onChange={(event) => setExpertise(event.target.value)} placeholder="多个领域用逗号分隔" /></label>
          <label className="form-field"><span>LLM 配置</span>
            <select value={llmProfileId} onChange={(event) => setLlmProfileId(event.target.value)} required>
              <option value="">请选择 LLM 配置</option>
              {llmProfiles.map((profile) => <option value={profile.id} key={profile.id}>{profile.name} · {profile.model}</option>)}
            </select>
          </label>
          <fieldset className="form-field form-fieldset"><legend>可用工具</legend>
            {tools.length === 0 && <p className="form-hint">当前没有可配置工具。</p>}
            <div className="checkbox-grid">{tools.map((tool) => <label className="checkbox-option" key={tool.name}><input type="checkbox" checked={selectedTools.includes(tool.name)} onChange={() => toggleTool(tool.name)} /><span>{tool.name}</span></label>)}</div>
          </fieldset>
          <label className="form-field"><span>权限模式</span>
            <select value={permissionMode} onChange={(event) => setPermissionMode(event.target.value)}><option value="PLAN">PLAN · 只读规划</option><option value="BUILD">BUILD · 按权限执行</option><option value="YOLO">YOLO · 宽松执行</option></select>
          </label>
          <label className="checkbox-option"><input type="checkbox" checked={isEnabled} onChange={(event) => setIsEnabled(event.target.checked)} /><span>启用此角色</span></label>
          {(formError || error) && <p className="inline-error" role="alert">{formError || error}</p>}
          <div className="dialog-actions"><Button type="button" onClick={onClose}>取消</Button><Button type="submit" variant="primary" disabled={isSubmitting} icon={<Plus size={16} />}>{isSubmitting ? "创建中…" : "创建角色"}</Button></div>
        </form>
      </div>
    </div>
  );
}
