import { useEffect, useState, type FormEvent } from "react";
import { Pencil, Plus, X } from "lucide-react";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import type { CreateMcpServerRequest, McpAuthMode, McpServerSummary, UpdateMcpServerRequest } from "../../../api/types";

interface Props {
  isOpen: boolean;
  server?: McpServerSummary | null;
  revision?: string;
  isSubmitting: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (request: CreateMcpServerRequest | UpdateMcpServerRequest) => void;
}

function parseMap(value: string): Record<string, string> {
  if (!value.trim()) return {};
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("必须是 JSON 对象");
  return parsed as Record<string, string>;
}

/** MCP Server 新增和编辑弹窗；本地与远程字段显式分离。 */
export function CreateMcpDialog({ isOpen, server = null, revision = "", isSubmitting, error, onClose, onSubmit }: Props) {
  const dialogRef = useModalFocus<HTMLDivElement>(isOpen);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isLocal, setIsLocal] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [cwd, setCwd] = useState("");
  const [env, setEnv] = useState("");
  const [url, setUrl] = useState("");
  const [headers, setHeaders] = useState("");
  const [authMode, setAuthMode] = useState<McpAuthMode>("none");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setName(server?.name ?? ""); setDescription(server?.description ?? ""); setIsLocal(server?.isLocal ?? true); setEnabled(server?.enabled ?? true);
    setCommand(server?.command ?? ""); setArgs(server?.args.join("\n") ?? ""); setCwd(server?.cwd ?? ""); setEnv(server ? JSON.stringify(server.env, null, 2) : "");
    setUrl(server?.url ?? ""); setHeaders(server ? JSON.stringify(server.headers, null, 2) : ""); setAuthMode(server?.authMode ?? "none"); setFormError(null);
  }, [isOpen, server?.id]);

  if (!isOpen) return null;
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setFormError(null);
    try {
      const base = { name: name.trim(), description: description.trim(), isLocal, enabled };
      const request: CreateMcpServerRequest = isLocal
        ? { ...base, command: command.trim(), args: args.split("\n").map((item) => item.trim()).filter(Boolean), cwd: cwd.trim() || null, env: parseMap(env) }
        : { ...base, url: url.trim(), headers: parseMap(headers), authMode };
      onSubmit(server ? { ...request, revision } : request);
    } catch (cause) { setFormError(cause instanceof Error ? cause.message : "配置格式无效"); }
  };
  return <div className="dialog-backdrop"><div ref={dialogRef} className="permission-dialog create-dialog" role="dialog" aria-modal="true" aria-labelledby="mcp-dialog-title" tabIndex={-1}>
    <div className="dialog-heading"><div><p className="eyebrow">MCP 服务</p><h2 id="mcp-dialog-title">{server ? "编辑 MCP 服务" : "新增 MCP 服务"}</h2></div><Button variant="ghost" aria-label="关闭" icon={<X size={17} />} onClick={onClose} /></div>
    <form className="form-stack" onSubmit={handleSubmit}>
      <label className="form-field"><span>名称</span><input value={name} onChange={(event) => setName(event.target.value)} required autoFocus /></label>
      <label className="form-field"><span>描述</span><input value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <label className="form-field"><span>类型</span><select value={isLocal ? "local" : "remote"} onChange={(event) => setIsLocal(event.target.value === "local")} disabled={Boolean(server)}><option value="local">本地 stdio</option><option value="remote">远程 Streamable HTTP</option></select></label>
      {isLocal ? <>
        <label className="form-field"><span>启动命令</span><input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="python" required /></label>
        <label className="form-field"><span>参数（每行一个）</span><textarea value={args} onChange={(event) => setArgs(event.target.value)} rows={3} /></label>
        <label className="form-field"><span>工作目录</span><input value={cwd} onChange={(event) => setCwd(event.target.value)} /></label>
        <label className="form-field"><span>环境变量 JSON</span><textarea value={env} onChange={(event) => setEnv(event.target.value)} rows={3} placeholder='{"KEY":"value"}' /></label>
      </> : <>
        <label className="form-field"><span>服务地址</span><input type="url" value={url} onChange={(event) => setUrl(event.target.value)} required placeholder="https://example.com/mcp" /></label>
        <label className="form-field"><span>请求头 JSON</span><textarea value={headers} onChange={(event) => setHeaders(event.target.value)} rows={3} placeholder='{"X-API-Key":"..."}' /></label>
        <label className="form-field"><span>认证模式</span><select value={authMode} onChange={(event) => setAuthMode(event.target.value as McpAuthMode)}><option value="none">无</option><option value="bearer">Bearer</option><option value="oauth">OAuth</option></select></label>
        {authMode === "oauth" && <p className="form-notice">OAuth 协议基础设施已就绪，浏览器授权入口将在授权 UI 接入后显示。</p>}
      </>}
      <label className="checkbox-option"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /><span>允许角色使用</span></label>
      {(formError || error) && <p className="inline-error" role="alert">{formError || error}</p>}
      <div className="dialog-actions"><Button type="button" onClick={onClose}>取消</Button><Button type="submit" variant="primary" disabled={isSubmitting} icon={server ? <Pencil size={16} /> : <Plus size={16} />}>{isSubmitting ? "保存中…" : server ? "保存修改" : "新增服务"}</Button></div>
    </form>
  </div></div>;
}
