import { useEffect, useState, type FormEvent } from "react";
import { Eye, EyeOff, Pencil, Plus, RefreshCw, X } from "lucide-react";
import { Button } from "../../../components/Button";
import { IconButton } from "../../../components/IconButton";
import { useModalFocus } from "../../../hooks/useModalFocus";
import type {
  CreateLLMProfileRequest,
  LLMProfileSummary,
  UpdateLLMProfileRequest,
} from "../../../api/types";
import { discoverDraftModels, getLlmProfileApiKey, listSavedLlmProfileModels } from "../api";

interface SharedLlmDialogProps {
  isOpen: boolean;
  isSubmitting: boolean;
  error: string | null;
  onClose: () => void;
}

interface CreateLlmDialogProps extends SharedLlmDialogProps {
  mode: "create";
  onSubmit: (request: CreateLLMProfileRequest) => void;
}

interface EditLlmDialogProps extends SharedLlmDialogProps {
  mode: "edit";
  profile: LLMProfileSummary;
  onSubmit: (request: UpdateLLMProfileRequest) => void;
}

type LlmDialogProps = CreateLlmDialogProps | EditLlmDialogProps;

/** LLM 配置新增和编辑弹窗；编辑时默认遮蔽回显已保存的 API Key。 */
export function CreateLlmDialog(props: LlmDialogProps) {
  const { isOpen, isSubmitting, error, onClose, mode } = props;
  const editProfile = mode === "edit" ? props.profile : null;
  const dialogRef = useModalFocus<HTMLDivElement>(isOpen);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false);
  const [isLoadingApiKey, setIsLoadingApiKey] = useState(false);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [options, setOptions] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setName(editProfile?.name ?? "");
    setBaseUrl(editProfile?.baseUrl ?? "");
    setModel(editProfile?.model ?? "");
    setApiKey("");
    setIsApiKeyVisible(false);
    setModelOptions(editProfile?.model ? [editProfile.model] : []);
    setOptions(editProfile ? JSON.stringify(editProfile.options, null, 2) : "");
    setFormError(null);
  }, [isOpen, mode, editProfile?.id]);

  useEffect(() => {
    if (!isOpen || mode !== "edit") return;
    let isCurrent = true;
    setIsLoadingApiKey(true);
    void getLlmProfileApiKey(props.profile.id)
      .then((response) => {
        if (isCurrent) setApiKey(response.apiKey);
      })
      .catch((requestError: unknown) => {
        if (isCurrent) setFormError(requestError instanceof Error ? requestError.message : "无法读取 API Key，请稍后重试");
      })
      .finally(() => {
        if (isCurrent) setIsLoadingApiKey(false);
      });
    return () => { isCurrent = false; };
  }, [isOpen, mode, editProfile?.id]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleRefreshModels = async () => {
    setFormError(null);
    setIsLoadingModels(true);
    try {
      const result = mode === "edit"
        ? await listSavedLlmProfileModels(props.profile.id)
        : await discoverDraftModels({ provider: "openai", baseUrl: baseUrl.trim() || null, apiKey: apiKey.trim() });
      setModelOptions((current) => Array.from(new Set([...current, ...result.models])).sort());
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "无法获取模型列表，请稍后重试");
    } finally {
      setIsLoadingModels(false);
    }
  };

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
    const commonFields = {
      name: name.trim(),
      provider: "openai" as const,
      baseUrl: baseUrl.trim() || null,
      model: model.trim(),
      options: parsedOptions,
    };
    if (mode === "edit") {
      props.onSubmit({
        ...commonFields,
        ...(apiKey.trim() ? { apiKey: apiKey.trim() } : {}),
      });
      return;
    }
    props.onSubmit({ ...commonFields, apiKey: apiKey.trim() });
  };

  return (
    <div className="dialog-backdrop">
      <div ref={dialogRef} className="permission-dialog create-dialog" role="dialog" aria-modal="true" aria-labelledby="llm-dialog-title" tabIndex={-1}>
        <div className="dialog-heading">
          <div><p className="eyebrow">模型连接</p><h2 id="llm-dialog-title">{mode === "edit" ? "编辑 LLM 配置" : "新增 LLM 配置"}</h2></div>
          <Button variant="ghost" aria-label="关闭" icon={<X size={17} />} onClick={onClose} />
        </div>
        <p className="form-notice">{mode === "edit" ? "已保存的 API Key 默认遮蔽显示，可通过右侧图标切换显示。" : "API Key 将保存到本地工作区数据库，列表和非编辑接口不会显示其内容。"}</p>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="form-field"><span>配置名称</span><input value={name} onChange={(event) => setName(event.target.value)} required autoFocus /></label>
          <label className="form-field"><span>服务商</span><select value="openai" onChange={() => undefined}><option value="openai">OpenAI 兼容</option></select></label>
          <label className="form-field"><span>Base URL</span><input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" /></label>
          <div className="form-field"><div className="form-field__label-row"><span id="llm-model-label">模型</span><IconButton type="button" label="刷新模型列表" disabled={isLoadingModels || isSubmitting} onClick={() => { void handleRefreshModels(); }}><RefreshCw className={isLoadingModels ? "spin" : undefined} size={16} /></IconButton></div><select id="llm-model" aria-labelledby="llm-model-label" value={model} onChange={(event) => setModel(event.target.value)} required><option value="" disabled>请选择模型</option>{modelOptions.map((option) => <option value={option} key={option}>{option}</option>)}</select></div>
          <div className="form-field"><div className="form-field__label-row"><span id="llm-api-key-label">API Key</span><IconButton type="button" label={isApiKeyVisible ? "隐藏 API Key" : "显示 API Key"} disabled={!apiKey || isLoadingApiKey} onClick={() => setIsApiKeyVisible((current) => !current)}>{isApiKeyVisible ? <EyeOff size={16} /> : <Eye size={16} />}</IconButton></div><input aria-labelledby="llm-api-key-label" type={isApiKeyVisible ? "text" : "password"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="sk-..." required={mode === "create"} disabled={isLoadingApiKey} autoComplete="off" /></div>
          <label className="form-field"><span>额外参数 JSON</span><textarea value={options} onChange={(event) => setOptions(event.target.value)} placeholder='{"temperature": 0.2}' rows={3} /></label>
          {(formError || error) && <p className="inline-error" role="alert">{formError || error}</p>}
          <div className="dialog-actions"><Button type="button" onClick={onClose}>取消</Button><Button type="submit" variant="primary" disabled={isSubmitting || isLoadingApiKey} icon={mode === "edit" ? <Pencil size={16} /> : <Plus size={16} />}>{isSubmitting ? "保存中…" : mode === "edit" ? "保存修改" : "创建配置"}</Button></div>
        </form>
      </div>
    </div>
  );
}
