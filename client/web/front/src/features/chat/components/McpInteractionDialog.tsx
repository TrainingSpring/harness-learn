import { useState } from "react";
import { Button } from "../../../components/Button";

export function McpInteractionDialog({
  interaction,
  onSubmit,
}: {
  interaction: { interactionType: "sampling" | "elicitation"; requestId: string; payload: Record<string, unknown> };
  onSubmit: (result: Record<string, unknown>) => void;
}) {
  const [value, setValue] = useState("");
  const message = typeof interaction.payload.message === "string"
    ? interaction.payload.message
    : interaction.interactionType === "sampling" ? "MCP Server 请求一次模型采样" : "MCP Server 需要你的输入";
  return <div className="dialog-backdrop"><div className="permission-dialog" role="dialog" aria-modal="true" aria-labelledby="mcp-interaction-title">
    <div className="dialog-heading"><div><p className="eyebrow">MCP 交互</p><h2 id="mcp-interaction-title">{interaction.interactionType === "sampling" ? "模型采样请求" : "需要输入"}</h2></div></div>
    <p>{message}</p>
    <label className="form-field"><span>回复</span><textarea value={value} onChange={(event) => setValue(event.target.value)} rows={4} /></label>
    <div className="dialog-actions"><Button onClick={() => onSubmit({ action: "cancel" })}>取消</Button><Button variant="primary" onClick={() => onSubmit({ action: "accept", content: { type: "text", text: value } })}>提交</Button></div>
  </div></div>;
}
