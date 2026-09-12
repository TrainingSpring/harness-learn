import type { ReactNode } from "react";

/** 列表无数据时的紧凑提示，不伪造不可用操作。 */
export function EmptyState({ icon, title, description }: { icon?: ReactNode; title: string; description: string }) {
  return (
    <div className="state-view" role="status">
      {icon && <div className="state-view__icon">{icon}</div>}
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}
