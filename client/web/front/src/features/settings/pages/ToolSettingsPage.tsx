import { useQuery } from "@tanstack/react-query";
import { Wrench } from "lucide-react";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { listTools } from "../api";

/** 已注册工具的只读元数据列表。 */
export function ToolSettingsPage() {
  const tools = useQuery({ queryKey: ["tools"], queryFn: listTools });
  return <div className="settings-section"><div><h2>工具</h2><p>当前 Runtime 可装配的工具及其权限动作。</p></div>
    {tools.isLoading && <Skeleton rows={4} />}
    {tools.isError && <ErrorState message={tools.error.message} onRetry={() => { void tools.refetch(); }} />}
    {tools.data?.items.length === 0 && <EmptyState icon={<Wrench />} title="尚未注册工具" description="当前工具目录为空。" />}
    {tools.data && <div className="tool-list">{tools.data.items.map((tool) => {
      const properties = (tool.inputSchema.properties ?? {}) as Record<string, unknown>;
      return <article className="tool-row" key={tool.name}><div><h3><code>{tool.name}</code></h3><p>{tool.description}</p></div><div className="tool-row__meta"><span>{Object.keys(properties).length} 个参数</span><code>{tool.permissionAction || "无需权限"}</code></div></article>;
    })}</div>}
  </div>;
}
