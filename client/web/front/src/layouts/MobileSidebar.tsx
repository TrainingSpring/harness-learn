import { X } from "lucide-react";
import { useEffect } from "react";
import { IconButton } from "../components/IconButton";
import { useModalFocus } from "../hooks/useModalFocus";
import { Sidebar } from "./Sidebar";

/** 小屏抽屉；支持遮罩点击与 Escape 关闭。 */
export function MobileSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const panel = useModalFocus<HTMLDivElement>(open);
  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="mobile-sidebar" role="presentation">
      <button className="mobile-sidebar__backdrop" aria-label="关闭导航" onClick={onClose} />
      <div ref={panel} className="mobile-sidebar__panel" role="dialog" aria-modal="true" aria-label="导航菜单" tabIndex={-1}>
        <IconButton label="关闭导航" className="mobile-sidebar__close" onClick={onClose}><X size={18} /></IconButton>
        <Sidebar onNavigate={onClose} />
      </div>
    </div>
  );
}
