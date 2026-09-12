/** 用户消息保持紧凑靠右，不使用高饱和聊天气泡。 */
export function UserMessage({ text }: { text: string }) {
  return <div className="message message--user"><div>{text}</div></div>;
}
