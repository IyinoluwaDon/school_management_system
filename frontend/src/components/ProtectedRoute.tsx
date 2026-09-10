import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { Role } from "../types";
import { useAuthStore } from "../store/auth";

export function ProtectedRoute({ allowedRoles }: { allowedRoles?: Role[] }) {
  const user = useAuthStore((state) => state.user);
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (allowedRoles && !allowedRoles.includes(user.role)) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}
