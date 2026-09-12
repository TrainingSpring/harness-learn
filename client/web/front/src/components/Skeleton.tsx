/** 固定尺寸的加载占位，避免内容加载时发生布局跳动。 */
export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-list" aria-busy="true" aria-label="正在加载">
      {Array.from({ length: rows }, (_, index) => <div className="skeleton" key={index} />)}
    </div>
  );
}
