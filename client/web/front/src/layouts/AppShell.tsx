import { Menu } from "lucide-react";
import { useState } from "react";
import { Outlet } from "react-router-dom";
import { IconButton } from "../components/IconButton";
import { MobileSidebar } from "./MobileSidebar";
import { Sidebar } from "./Sidebar";

/** 全部页面共享的稳定工作区骨架，路由切换不会重新挂载侧栏。 */
export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="app-shell">
      <div className="app-shell__desktop-sidebar"><Sidebar /></div>
      <header className="mobile-header">
        <IconButton label="打开导航" onClick={() => setMobileOpen(true)}><Menu size={19} /></IconButton>
        <span><span className="brand-mark">H</span> Harness</span>
      </header>
      <MobileSidebar open={mobileOpen} onClose={() => setMobileOpen(false)} />
      <main className="app-shell__content"><Outlet /></main>
    </div>
  );
}
