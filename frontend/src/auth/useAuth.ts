import { useCallback, useEffect, useState } from "react";
import {
  AUTH_EXPIRED_EVENT,
  changePassword as apiChangePassword,
  getMe,
  getToken,
  login as apiLogin,
  loginWithLink as apiLoginWithLink,
  register as apiRegister,
  setToken,
} from "../api/client";
import type { User } from "../types";

type Status = "loading" | "anon" | "authed";

interface AuthState {
  status: Status;
  user: User | null;
  learnerId: string | null;
}

const ANON: AuthState = { status: "anon", user: null, learnerId: null };

export function useAuth() {
  const [state, setState] = useState<AuthState>(() => ({
    ...ANON,
    status: getToken() ? "loading" : "anon",
  }));

  // Resume a stored session on first load.
  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    getMe()
      .then((me) => {
        if (!cancelled) {
          setState({ status: "authed", user: me.user, learnerId: me.learner_id });
        }
      })
      .catch(() => {
        setToken(null);
        if (!cancelled) setState(ANON);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Drop to the login screen when a request reports the token is no longer valid.
  useEffect(() => {
    const onExpired = () => setState(ANON);
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await apiLogin(username, password);
    setToken(result.token);
    const me = await getMe();
    setState({ status: "authed", user: me.user, learnerId: me.learner_id });
  }, []);

  const loginWithLink = useCallback(async (token: string) => {
    const result = await apiLoginWithLink(token);
    setToken(result.token);
    const me = await getMe();
    setState({ status: "authed", user: me.user, learnerId: me.learner_id });
  }, []);

  const register = useCallback(
    (username: string, password: string) => apiRegister(username, password),
    [],
  );

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      const result = await apiChangePassword(currentPassword, newPassword);
      setToken(result.token);
      const me = await getMe();
      setState({ status: "authed", user: me.user, learnerId: me.learner_id });
    },
    [],
  );

  const logout = useCallback(() => {
    setToken(null);
    setState(ANON);
  }, []);

  const setLearnerId = useCallback((learnerId: string) => {
    setState((s) => ({ ...s, learnerId }));
  }, []);

  return { ...state, login, loginWithLink, register, changePassword, logout, setLearnerId };
}
