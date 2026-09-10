import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Bell, BookOpen, CalendarDays, CreditCard, LayoutDashboard, LogOut, ScanLine, Users } from "lucide-react";
import { roleLabels } from "../config/roles";
import { useAuthStore } from "../store/auth";

const links = [
  { to: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { to: "/attendance/scanner", label: "Attendance scanner", icon: ScanLine },
  { to: "/academics", label: "Academics", icon: BookOpen },
  { to: "/scheduling", label: "Scheduling", icon: CalendarDays },
  { to: "/finance", label: "Finance", icon: CreditCard },
  { to: "/users", label: "People", icon: Users },
  { to: "/announcements", label: "Announcements", icon: Bell },
];

export function AppLayout() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">N</span><div><strong>Northstar</strong><small>School portal</small></div></div>
        <nav>{links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}><Icon size={18} />{label}</NavLink>)}</nav>
        <div className="sidebar-footer"><div className="avatar">{user?.displayName.slice(0, 1) ?? "U"}</div><div className="user-meta"><strong>{user?.displayName}</strong><small>{user ? roleLabels[user.role] : ""}</small></div><button className="icon-button" aria-label="Log out" onClick={() => { logout(); navigate("/login"); }}><LogOut size={17} /></button></div>
      </aside>
      <main className="main-content"><header className="topbar"><div><span className="eyebrow">Monday, September 9, 2026</span><h1>Good morning, {user?.displayName.split(" ")[0] ?? "there"}</h1></div><div className="topbar-actions"><span className="status-dot">All systems operational</span><button className="icon-button"><Bell size={19} /></button></div></header><div className="page-content"><Outlet /></div></main>
    </div>
  );
}
