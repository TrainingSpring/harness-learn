import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

/** 数据请求失败时提供明确说明和可恢复操作。 */
export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state-view state-view--error" role="alert">
      <div className="state-view__icon"><AlertTriangle size={20} /></div>
      <h2>加载失败</h2>
      <p>{message}</p>
      <Button icon={<RefreshCw size={15} />} onClick={onRetry}>重试</Button>
    </div>
  );
}
