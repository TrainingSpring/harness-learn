import { useState } from "react";
import { Edit3, Play, Plus, RefreshCw, RotateCcw, Server, Square, Trash2 } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "../../../components/Button";
import { IconButton } from "../../../components/IconButton";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { createMcpServer, deleteMcpServer, listMcpServers, restartMcpServer, startMcpAuthorization, startMcpServer, stopMcpServer, updateMcpServer, revokeMcpAuthorization } from "../api";
import { CreateMcpDialog } from "../components/CreateMcpDialog";
import type { CreateMcpServerRequest, McpServerSummary, UpdateMcpServerRequest } from "../../../api/types";

const statusLabels: Record<string, string> = { remote: "远程", not_running: "未运行", starting: "启动中", running: "运行中", exited: "已退出", failed: "失败", stopped: "已停止" };

export function McpSettingsPage() {
  const [editing, setEditing] = useState<{ server: McpServerSummary; revision: string } | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const servers = useQuery({ queryKey: ["mcp-servers"], queryFn: listMcpServers });
  const refresh = () => { setNotice(null); void servers.refetch(); };
  const create = useMutation({ mutationFn: (request: CreateMcpServerRequest) => createMcpServer(request), onSuccess: async () => { await servers.refetch(); setIsCreateOpen(false); } });
  const update = useMutation({ mutationFn: (request: UpdateMcpServerRequest) => updateMcpServer(editing!.server.id, request), onSuccess: async () => { await servers.refetch(); setEditing(null); } });
  const remove = useMutation({ mutationFn: (server: McpServerSummary) => deleteMcpServer(server.id, servers.data!.revision), onSuccess: refresh });
  const action = useMutation({ mutationFn: ({ id, type }: { id: string; type: "start" | "stop" | "restart" }) => type === "start" ? startMcpServer(id) : type === "stop" ? stopMcpServer(id) : restartMcpServer(id), onSuccess: refresh });
  const oauthStart = useMutation({ mutationFn: startMcpAuthorization, onSuccess: (result) => { window.location.assign(result.authorizationUrl); } });
  const oauthRevoke = useMutation({ mutationFn: revokeMcpAuthorization, onSuccess: async () => { await servers.refetch(); } });

  return <div className="settings-section"><div className="settings-section__header"><div><h2>MCP 服务</h2><p>管理本地和远程 MCP Server。角色只能选择整个 Server，不能单独分配内部 Tool。</p></div><div className="settings-section__actions"><Button variant="primary" icon={<Plus size={16} />} onClick={() => setIsCreateOpen(true)}>新增服务</Button><IconButton label="刷新 MCP 服务" onClick={refresh} disabled={servers.isFetching}><RefreshCw size={17} className={servers.isFetching ? "spin" : undefined} /></IconButton></div></div>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    {servers.isLoading && <Skeleton rows={4} />}
    {servers.isError && <ErrorState message={servers.error.message} onRetry={refresh} />}
    {servers.data?.items.length === 0 && <EmptyState icon={<Server />} title="尚未配置 MCP 服务" description="新增一个本地或远程 MCP Server 后，角色即可在配置中选择它。" />}
    {servers.data && servers.data.items.length > 0 && <div className="mcp-list" role="list">{servers.data.items.map((server) => <article className="mcp-row" key={server.id}>
      <div className="mcp-row__identity"><span className="mcp-row__icon"><Server size={16} /></span><div><h3>{server.name}</h3><p>{server.description || (server.isLocal ? server.command : server.url)}</p><small>{server.id}</small></div></div>
      <div className="mcp-row__meta"><span className={`status ${server.status === "running" ? "status--ok" : server.status === "failed" ? "status--invalid" : "status--muted"}`}>{statusLabels[server.status] ?? server.status}</span><span>{server.isLocal ? "本地 stdio" : `远程 · ${server.authMode}`}</span></div>
      <div className="mcp-row__actions">{server.isLocal && <>{server.status === "running" ? <IconButton label={`停止 ${server.name}`} onClick={() => action.mutate({ id: server.id, type: "stop" })} disabled={action.isPending}><Square size={15} /></IconButton> : <IconButton label={`启动 ${server.name}`} onClick={() => action.mutate({ id: server.id, type: "start" })} disabled={action.isPending}><Play size={15} /></IconButton>}<IconButton label={`重启 ${server.name}`} onClick={() => action.mutate({ id: server.id, type: "restart" })} disabled={action.isPending}><RotateCcw size={15} /></IconButton></>}{!server.isLocal && server.authMode === "oauth" && <Button onClick={() => server.oauthAuthorized ? oauthRevoke.mutate(server.id) : oauthStart.mutate(server.id)}>{server.oauthAuthorized ? "撤销授权" : "授权"}</Button>}<IconButton label={`编辑 ${server.name}`} onClick={() => setEditing({ server, revision: servers.data?.revision ?? "" })}><Edit3 size={15} /></IconButton><IconButton label={`删除 ${server.name}`} className="icon-button--danger" onClick={() => { if (window.confirm(`确定删除 ${server.name}？`)) remove.mutate(server); }} disabled={remove.isPending}><Trash2 size={15} /></IconButton></div>
    </article>)}</div>}
    {action.error && <p className="inline-error" role="alert">{action.error.message}</p>}{remove.error && <p className="inline-error" role="alert">{remove.error.message}</p>}
    <CreateMcpDialog isOpen={isCreateOpen} isSubmitting={create.isPending} error={create.error?.message ?? null} onClose={() => setIsCreateOpen(false)} onSubmit={(request) => create.mutate(request as CreateMcpServerRequest)} />
    <CreateMcpDialog isOpen={Boolean(editing)} server={editing?.server} revision={editing?.revision} isSubmitting={update.isPending} error={update.error?.message ?? null} onClose={() => setEditing(null)} onSubmit={(request) => update.mutate(request as UpdateMcpServerRequest)} />
  </div>;
}
