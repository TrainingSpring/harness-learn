import { useQuery } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { Skeleton } from "../../../components/Skeleton";
import { PermissionDialog } from "../../permissions/components/PermissionDialog";
import { getSession, listMessages } from "../../sessions/api";
import { ChatHeader } from "../components/ChatHeader";
import { Composer } from "../components/Composer";
import { MessageList } from "../components/MessageList";
import { useChatRun } from "../hooks/useChatRun";

interface ChatNavigationState { initialMessage?: string }

/** 固定角色 1v1 对话工作区。 */
export function ChatPage() {
  const { sessionId = "" } = useParams();
  const location = useLocation();
  const initialSent = useRef(false);
  const [optimisticText, setOptimisticText] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session", sessionId], queryFn: () => getSession(sessionId), enabled: Boolean(sessionId) });
  const messages = useQuery({ queryKey: ["messages", sessionId], queryFn: () => listMessages(sessionId), enabled: Boolean(sessionId) });
  const run = useChatRun(sessionId);

  const send = async (text: string) => {
    setOptimisticText(text);
    await run.send(text);
    setOptimisticText(null);
  };

  useEffect(() => {
    const initialMessage = (location.state as ChatNavigationState | null)?.initialMessage;
    if (initialMessage && !initialSent.current && session.data) {
      initialSent.current = true;
      void send(initialMessage);
      window.history.replaceState({}, document.title);
    }
  }, [location.state, session.data]);

  if (session.isLoading || messages.isLoading) return <div className="workspace-page"><div className="page"><Skeleton rows={6} /></div></div>;
  if (session.isError) return <div className="page"><ErrorState message={session.error.message} onRetry={() => { void session.refetch(); }} /></div>;
  if (messages.isError) return <div className="page"><ErrorState message={messages.error.message} onRetry={() => { void messages.refetch(); }} /></div>;
  if (!session.data || !messages.data) return null;

  return (
    <div className="workspace-page chat-page">
      <ChatHeader agent={session.data.agent} status={run.status} />
      {messages.data.items.length === 0 && !optimisticText && !run.streamingText ? (
        <EmptyState icon={<MessageSquare />} title={`与 ${session.data.agent.name} 开始对话`} description="发送一条消息，建立这段会话的第一条上下文。" />
      ) : (
        <MessageList messages={messages.data.items} optimisticUserText={optimisticText} streamingText={run.streamingText} toolEvents={run.toolEvents} />
      )}
      <footer className="composer-dock">
        {run.error && <p className="inline-error" role="alert">{run.error}</p>}
        <Composer isRunning={run.status !== "idle"} onStop={() => { void run.stop(); }} onSend={(text) => { void send(text); }} />
      </footer>
      {run.permission && <PermissionDialog request={run.permission} isSubmitting={run.permissionSubmitting} onDecision={(decision, scope) => { void run.resolvePermission(decision, scope); }} />}
    </div>
  );
}
