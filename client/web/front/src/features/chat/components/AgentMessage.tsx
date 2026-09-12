import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** 安全渲染 Agent Markdown；禁用原始 HTML 和外部图片自动请求。 */
export function AgentMessage({ text, streaming = false }: { text: string; streaming?: boolean }) {
  return (
    <div className={`message message--agent ${streaming ? "message--streaming" : ""}`}>
      <div className="markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>,
            // 模型 Markdown 不是可信附件来源，不让 img 触发第三方网络请求。
            img: ({ alt = "" }) => <span className="markdown-image-alt">[图片：{alt || "未命名"}]</span>,
          }}
        >{text}</ReactMarkdown>
        {streaming && <span className="stream-caret" aria-label="正在生成" />}
      </div>
    </div>
  );
}
