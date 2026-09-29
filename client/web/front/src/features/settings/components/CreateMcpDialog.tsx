import { useEffect, useRef, useState, type FormEvent } from "react";
import { Folder, Pencil, Plus, X } from "lucide-react";
import { Button } from "../../../components/Button";
import { useModalFocus } from "../../../hooks/useModalFocus";
import { getMcpDirectoryMetadata } from "../api";
import type { CreateMcpServerRequest, McpAuthMode, McpServerSummary, UpdateMcpServerRequest } from "../../../api/types";
import { McpDirectoryPicker } from "./McpDirectoryPicker";

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
  const [directory, setDirectory] = useState("");
  const [env, setEnv] = useState("");
  const [url, setUrl] = useState("");
  const [headers, setHeaders] = useState("");
  const [authMode, setAuthMode] = useState<McpAuthMode>("none");
  const [oauthClientId, setOauthClientId] = useState("");
  const [oauthScopes, setOauthScopes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isDirectoryPickerOpen, setIsDirectoryPickerOpen] = useState(false);
  const nameWasAutoFilled = useRef(true);
  const descriptionWasAutoFilled = useRef(true);

  useEffect(() => {
    if (!isOpen) return;
    setName(server?.name ?? ""); setDescription(server?.description ?? ""); setIsLocal(server?.isLocal ?? true); setEnabled(server?.enabled ?? true);
    setCommand(server?.command ?? ""); setArgs(server?.args.join("\n") ?? ""); setDirectory(server?.directory ?? ""); setEnv(server ? JSON.stringify(server.env, null, 2) : "");
    setUrl(server?.url ?? ""); setHeaders(server ? JSON.stringify(server.headers, null, 2) : ""); setAuthMode(server?.authMode ?? "none"); setOauthClientId(""); setOauthScopes(""); setFormError(null);
    setIsDirectoryPickerOpen(false); nameWasAutoFilled.current = !server; descriptionWasAutoFilled.current = !server;
  }, [isOpen, server?.id]);

  if (!isOpen) return null;
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setFormError(null);
    try {
      const base = { name: name.trim(), description: description.trim(), isLocal, enabled };
      const request: CreateMcpServerRequest = isLocal
        ? { ...base, command: command.trim(), args: args.split("\n").map((item) => item.trim()).filter(Boolean), directory: directory.trim() || null, env: parseMap(env) }
        : { ...base, url: url.trim(), headers: parseMap(headers), authMode, oauthClientId: oauthClientId.trim() || null, oauthScopes: oauthScopes.split(/[,\n]/).map((item) => item.trim()).filter(Boolean) };
      onSubmit(server ? { ...request, revision } : request);
    } catch (cause) { setFormError(cause instanceof Error ? cause.message : "配置格式无效"); }
  };
  return <div className="dialog-backdrop"><div ref={dialogRef} className="permission-dialog create-dialog" role="dialog" aria-modal="true" aria-labelledby="mcp-dialog-title" tabIndex={-1}>
    <div className="dialog-heading"><div><p className="eyebrow">MCP 服务</p><h2 id="mcp-dialog-title">{server ? "编辑 MCP 服务" : "新增 MCP 服务"}</h2></div><Button variant="ghost" aria-label="关闭" icon={<X size={17} />} onClick={onClose} /></div>
    <form className="form-stack" onSubmit={handleSubmit}>
      <label className="form-field"><span>名称</span><input value={name} onChange={(event) => { setName(event.target.value); nameWasAutoFilled.current = false; }} required autoFocus /></label>
      <label className="form-field"><span>描述</span><input value={description} onChange={(event) => { setDescription(event.target.value); descriptionWasAutoFilled.current = false; }} /></label>
      <label className="form-field"><span>类型</span><select value={isLocal ? "local" : "remote"} onChange={(event) => setIsLocal(event.target.value === "local")} disabled={Boolean(server)}><option value="local">本地 stdio</option><option value="remote">远程 Streamable HTTP</option></select></label>
      {isLocal ? <>
        <label className="form-field"><span>启动命令</span><input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="python" required /></label>
        <label className="form-field"><span>参数（每行一个）</span><textarea value={args} onChange={(event) => setArgs(event.target.value)} rows={3} /></label>
        <label className="form-field"><span>MCP 服务目录</span><div className="form-field__input-action"><input value={directory} readOnly required placeholder="请选择 MCP 服务所在目录" /><Button type="button" variant="ghost" icon={<Folder size={16} />} onClick={() => setIsDirectoryPickerOpen(true)}>选择目录</Button></div></label>
        <label className="form-field"><span>环境变量 JSON</span><textarea value={env} onChange={(event) => setEnv(event.target.value)} rows={3} placeholder='{"KEY":"value"}' /></label>
      </> : <>
        <label className="form-field"><span>服务地址</span><input type="url" value={url} onChange={(event) => setUrl(event.target.value)} required placeholder="https://example.com/mcp" /></label>
        <label className="form-field"><span>请求头 JSON</span><textarea value={headers} onChange={(event) => setHeaders(event.target.value)} rows={3} placeholder='{"X-API-Key":"..."}' /></label>
        <label className="form-field"><span>认证模式</span><select value={authMode} onChange={(event) => setAuthMode(event.target.value as McpAuthMode)}><option value="none">无</option><option value="bearer">Bearer</option><option value="oauth">OAuth</option></select></label>
        {authMode === "oauth" && <><label className="form-field"><span>OAuth Client ID</span><input value={oauthClientId} onChange={(event) => setOauthClientId(event.target.value)} /></label><label className="form-field"><span>OAuth Scopes</span><input value={oauthScopes} onChange={(event) => setOauthScopes(event.target.value)} placeholder="多个 scope 用逗号分隔" /></label><p className="form-notice">保存后可在服务列表发起浏览器授权。</p></>}
      </>}
      <label className="checkbox-option"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /><span>启用服务</span></label>
      {(formError || error) && <p className="inline-error" role="alert">{formError || error}</p>}
      <div className="dialog-actions"><Button type="button" onClick={onClose}>取消</Button><Button type="submit" variant="primary" disabled={isSubmitting} icon={server ? <Pencil size={16} /> : <Plus size={16} />}>{isSubmitting ? "保存中…" : server ? "保存修改" : "新增服务"}</Button></div>
    </form>
    {isDirectoryPickerOpen && <McpDirectoryPicker selectedPath={directory || null} onClose={() => setIsDirectoryPickerOpen(false)} onSelect={(path) => {
      setIsDirectoryPickerOpen(false);
      if (!path) return;
      setDirectory(path);
      void getMcpDirectoryMetadata(path).then((metadata) => {
        if (nameWasAutoFilled.current) setName(metadata.name);
        if (descriptionWasAutoFilled.current) setDescription(metadata.description);
      }).catch((cause) => setFormError(cause instanceof Error ? cause.message : "无法读取 MCP 服务目录信息"));
    }} />}
  </div></div>;
}
