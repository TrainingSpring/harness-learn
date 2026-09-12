import { CheckCircle2, ChevronRight, LoaderCircle, Wrench } from "lucide-react";
import type { ToolEventData } from "../../../api/types";

/** 工具调用折叠为执行记录，避免与自然语言消息混淆。 */
export function ToolEvent({ event, completed }: { event: ToolEventData; completed: boolean }) {
  return (
    <details className="tool-event">
      <summary>
        <ChevronRight className="tool-event__chevron" size={15} />
        <Wrench size={15} />
        <strong>{event.toolName}</strong>
        <span>{completed ? "已完成" : "执行中"}</span>
        {completed ? <CheckCircle2 className="tool-event__done" size={15} /> : <LoaderCircle className="spin" size={15} />}
      </summary>
      <div className="tool-event__body">
        {event.summary ? <pre>{event.summary}</pre> : <p>暂无可展示的执行摘要。</p>}
        {event.durationMs !== undefined && <small>耗时 {event.durationMs} ms</small>}
      </div>
    </details>
  );
}
