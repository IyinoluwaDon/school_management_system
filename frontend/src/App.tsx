import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AppLayout } from "./layouts/AppLayout";
import { LoginPage } from "./features/auth/LoginPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { ScannerPage } from "./features/attendance/ScannerPage";
import { SchedulingPage } from "./features/scheduling/SchedulingPage";
import { useAuthStore } from "./store/auth";
import "./styles.css";

const queryClient = new QueryClient();

function Placeholder({ title, description }: { title: string; description: string }) {
  return <section><span className="eyebrow">Workspace</span><h2>{title}</h2><p className="muted">{description}</p><div className="empty-state"><strong>This module is ready for API wiring.</strong><span>The backend endpoint and typed feature boundary are already in place for the next sprint.</span></div></section>;
}

function useSessionExpiryHandler() {
  const logout = useAuthStore((state) => state.logout);
  useEffect(() => {
    const handleUnauthorized = () => logout();
    window.addEventListener("school:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("school:unauthorized", handleUnauthorized);
  }, [logout]);
}

export function App() {
  useSessionExpiryHandler();
  return <QueryClientProvider client={queryClient}><BrowserRouter><Routes><Route path="/login" element={<LoginPage />} /><Route element={<ProtectedRoute />}><Route element={<AppLayout />}><Route path="/dashboard" element={<DashboardPage />} /><Route path="/attendance/scanner" element={<ScannerPage />} /><Route path="/academics" element={<Placeholder title="Academics" description="Assessments, grades, approvals, and report cards." />} /><Route path="/scheduling" element={<SchedulingPage />} /><Route path="/finance" element={<Placeholder title="Finance" description="Fees, invoices, payments, and receipts." />} /><Route path="/users" element={<Placeholder title="People" description="Students, staff, parents, and role access." />} /><Route path="/announcements" element={<Placeholder title="Announcements" description="Keep families and staff informed." />} /></Route></Route><Route path="*" element={<Navigate to="/dashboard" replace />} /></Routes></BrowserRouter></QueryClientProvider>;
}
