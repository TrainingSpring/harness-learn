import { ArrowDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ContextItemResponse, ToolEventData } from "../../../api/types";
import { IconButton } from "../../../components/IconButton";
import { AgentMessage } from "./AgentMessage";
import { ToolEvent } from "./ToolEvent";
import { UserMessage } from "./UserMessage";

function payloadText(item: ContextItemResponse): string {
  return typeof item.payload.text === "string" ? item.payload.text : "";
}

function outputSummary(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (value === undefined) return undefined;
  try {
    return JSON.stringify(value);
  } catch {
    return "结果无法序列化";
  }
}

/** 消息时间线，只有用户停留在底部附近时才跟随新 token。 */
export function MessageList({ messages, optimisticUserText, streamingText, toolEvents }: {
  messages: ContextItemResponse[];
  optimisticUserText: string | null;
  streamingText: string;
  toolEvents: { data: ToolEventData; completed: boolean }[];
}) {
  const scrollArea = useRef<HTMLDivElement>(null);
  const [following, setFollowing] = useState(true);

  useEffect(() => {
    if (following) scrollArea.current?.scrollTo({ top: scrollArea.current.scrollHeight });
  }, [messages, optimisticUserText, streamingText, toolEvents, following]);

  const handleScroll = () => {
    const element = scrollArea.current;
    if (!element) return;
    setFollowing(element.scrollHeight - element.scrollTop - element.clientHeight < 80);
  };

  const outputs = new Map(
    messages
      .filter((item) => item.kind === "FUNCTION_CALL_OUTPUT" && item.callId)
      .map((item) => [item.callId as string, item]),
  );

  return (
    <div className="message-scroll" ref={scrollArea} onScroll={handleScroll} role="log" aria-live="polite" aria-relevant="additions text">
      <div className="message-list">
        {messages.map((item) => {
          if (item.kind === "USER_MESSAGE") return <UserMessage key={item.id} text={payloadText(item)} />;
          if (item.kind === "AGENT_MESSAGE") return <AgentMessage key={item.id} text={payloadText(item)} />;
          if (item.kind === "FUNCTION_CALL") {
            const output = item.callId ? outputs.get(item.callId) : undefined;
            return <ToolEvent key={item.id} completed={Boolean(output)} event={{ callId: item.callId ?? item.id, toolName: String(item.payload.name ?? "tool"), summary: outputSummary(output?.payload.output) }} />;
          }
          if (item.kind === "FUNCTION_CALL_OUTPUT") return null;
          return null;
        })}
        {optimisticUserText && <UserMessage text={optimisticUserText} />}
        {toolEvents.map((event) => <ToolEvent key={event.data.callId} {...event} event={event.data} />)}
        {streamingText && <AgentMessage text={streamingText} streaming />}
      </div>
      {!following && <IconButton label="回到底部" className="scroll-bottom" onClick={() => { setFollowing(true); scrollArea.current?.scrollTo({ top: scrollArea.current.scrollHeight, behavior: "smooth" }); }}><ArrowDown size={17} /></IconButton>}
    </div>
  );
}
