import { useEffect, useState, type FormEvent } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import type { CreateLLMProfileRequest } from "../../../api/types";

interface CreateLlmDialogProps {
  isOpen: boolean;
  isSubmitting: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (request: CreateLLMProfileRequest) => void;
}

/** LLM 配置创建弹窗；只提交 credentialRef，不处理真实凭据值。 */
export function CreateLlmDialog({ isOpen, isSubmitting, error, onClose, onSubmit }: CreateLlmDialogProps) {
  const dialogRef = useModalFocus<HTMLDivElement>(isOpen);
  const [name, setName] = useState("");
  const [provider, setProvider] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [credentialRef, setCredentialRef] = useState("");
  const [options, setOptions] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setName("");
    setProvider("");
    setBaseUrl("");
    setModel("");
    setCredentialRef("");
    setOptions("");
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

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    let parsedOptions: Record<string, unknown> = {};
    if (options.trim()) {
      try {
        const parsed: unknown = JSON.parse(options);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error("对象格式");
        parsedOptions = parsed as Record<string, unknown>;
      } catch {
        setFormError("额外参数必须是有效的 JSON 对象");
        return;
      }
    }
    onSubmit({
      name: name.trim(),
      provider: provider.trim(),
      baseUrl: baseUrl.trim() || null,
      model: model.trim(),
      credentialRef: credentialRef.trim(),
      options: parsedOptions,
    });
  };

  return (
    <div className="dialog-backdrop">
      <div ref={dialogRef} className="permission-dialog create-dialog" role="dialog" aria-modal="true" aria-labelledby="create-llm-title" tabIndex={-1}>
        <div className="dialog-heading">
          <div><p className="eyebrow">模型连接</p><h2 id="create-llm-title">新增 LLM 配置</h2></div>
          <Button variant="ghost" aria-label="关闭" icon={<X size={17} />} onClick={onClose} />
        </div>
        <p className="form-notice">请填写凭据引用，例如 <code>env:OPENAI_API_KEY</code>，不要填写真实 API Key。</p>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="form-field"><span>配置名称</span><input value={name} onChange={(event) => setName(event.target.value)} required autoFocus /></label>
          <label className="form-field"><span>服务商</span><input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="openai" required /></label>
          <label className="form-field"><span>Base URL</span><input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" /></label>
          <label className="form-field"><span>模型</span><input value={model} onChange={(event) => setModel(event.target.value)} placeholder="gpt-5" required /></label>
          <label className="form-field"><span>凭据引用</span><input value={credentialRef} onChange={(event) => setCredentialRef(event.target.value)} placeholder="env:OPENAI_API_KEY" required /></label>
          <label className="form-field"><span>额外参数 JSON</span><textarea value={options} onChange={(event) => setOptions(event.target.value)} placeholder='{"temperature": 0.2}' rows={3} /></label>
          {(formError || error) && <p className="inline-error" role="alert">{formError || error}</p>}
          <div className="dialog-actions"><Button type="button" onClick={onClose}>取消</Button><Button type="submit" variant="primary" disabled={isSubmitting} icon={<Plus size={16} />}>{isSubmitting ? "创建中…" : "创建配置"}</Button></div>
        </form>
      </div>
    </div>
  );
}
