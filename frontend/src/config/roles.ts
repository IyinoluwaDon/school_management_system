import type { Role } from "../types";

export const roleLabels: Record<Role, string> = {
  SUPER_ADMIN: "Super Administrator",
  PRINCIPAL: "Principal",
  TEACHER: "Teacher",
  ACCOUNTANT: "Accountant",
  HR: "HR Officer",
  STUDENT: "Student",
  PARENT: "Parent / Guardian",
};

export const dashboardPath: Record<Role, string> = {
  SUPER_ADMIN: "/dashboard",
  PRINCIPAL: "/dashboard",
  TEACHER: "/dashboard",
  ACCOUNTANT: "/dashboard",
  HR: "/dashboard",
  STUDENT: "/dashboard",
  PARENT: "/dashboard",
};
