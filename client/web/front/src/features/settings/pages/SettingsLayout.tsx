import { Outlet } from "react-router-dom";
import { SettingsNav } from "../components/SettingsNav";

/** 设置页面共享的标题和分类导航。 */
export function SettingsLayout() {
  return (
    <div className="page settings-page">
      <header className="page-header"><div><p className="eyebrow">偏好与配置</p><h1>设置</h1></div></header>
      <div className="settings-layout"><SettingsNav /><section className="settings-content"><Outlet /></section></div>
    </div>
  );
}
