import { create } from "zustand";
import type { AuthenticatedUser, Role, UserSession } from "../types";

interface AuthState {
  user: UserSession | null;
  accessToken: string | null;
  refreshToken: string | null;
  setSession: (user: AuthenticatedUser, accessToken: string, refreshToken: string) => void;
  setAccessToken: (accessToken: string) => void;
  logout: () => void;
}

function toSession(user: AuthenticatedUser): UserSession {
  return { username: user.username, displayName: user.full_name, role: user.role as Role };
}

const storedUser = localStorage.getItem("school_user");
const storedAccessToken = localStorage.getItem("school_access_token");
const storedRefreshToken = localStorage.getItem("school_refresh_token");

export const useAuthStore = create<AuthState>((set) => ({
  user: storedUser ? (JSON.parse(storedUser) as UserSession) : null,
  accessToken: storedAccessToken,
  refreshToken: storedRefreshToken,
  setSession: (user, accessToken, refreshToken) => {
    const session = toSession(user);
    localStorage.setItem("school_user", JSON.stringify(session));
    localStorage.setItem("school_access_token", accessToken);
    localStorage.setItem("school_refresh_token", refreshToken);
    set({ user: session, accessToken, refreshToken });
  },
  setAccessToken: (accessToken) => {
    localStorage.setItem("school_access_token", accessToken);
    set({ accessToken });
  },
  logout: () => {
    localStorage.removeItem("school_user");
    localStorage.removeItem("school_access_token");
    localStorage.removeItem("school_refresh_token");
    set({ user: null, accessToken: null, refreshToken: null });
  },
}));
