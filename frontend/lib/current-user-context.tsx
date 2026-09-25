"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { api, getToken } from "@/lib/api";
import type { CurrentUser } from "@/lib/types";

type CurrentUserState = {
  user: CurrentUser | null;
  isStaff: boolean;
  loading: boolean;
};

const CurrentUserContext = createContext<CurrentUserState>({
  user: null,
  isStaff: false,
  loading: true,
});

// A transient failure (network blip, a momentarily cold backend) must not
// permanently hide admin-only nav (e.g. the Users tab) for the rest of the
// tab session — retry a few times with backoff before giving up, and try
// again on refocus in case the backend has recovered since.
const RETRY_DELAYS_MS = [1000, 3000, 8000];

let cachedUser: CurrentUser | null = null;
let cachedFetchFailed = false;

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CurrentUserState>({
    user: cachedUser,
    isStaff: cachedUser?.is_staff ?? false,
    loading: cachedUser === null && !cachedFetchFailed,
  });
  const requested = useRef(cachedUser !== null);
  const fetchInFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;

    function fetchUser(attempt = 0) {
      requested.current = true;
      fetchInFlight.current = true;
      setState((s) => ({ ...s, loading: true }));
      api
        .me()
        .then((currentUser) => {
          if (cancelled) return;
          cachedUser = currentUser;
          cachedFetchFailed = false;
          setState({ user: currentUser, isStaff: currentUser.is_staff, loading: false });
        })
        .catch(() => {
          if (cancelled) return;
          if (attempt < RETRY_DELAYS_MS.length) {
            window.setTimeout(() => fetchUser(attempt + 1), RETRY_DELAYS_MS[attempt]);
            return;
          }
          cachedFetchFailed = true;
          setState({ user: null, isStaff: false, loading: false });
        })
        .finally(() => {
          fetchInFlight.current = false;
        });
    }

    if (!requested.current) fetchUser();

    // A login/logout in this tab means the account may have changed —
    // without this, the cached is_staff from the previous account kept
    // hiding (or wrongly showing) the Users nav tab after switching accounts.
    function handleAuthChanged() {
      cachedUser = null;
      cachedFetchFailed = false;
      requested.current = false;
      if (getToken()) {
        fetchUser();
      } else {
        setState({ user: null, isStaff: false, loading: false });
      }
    }
    window.addEventListener("auth-changed", handleAuthChanged);

    function handleVisibilityChange() {
      if (document.visibilityState === "visible" && cachedFetchFailed && !fetchInFlight.current) {
        fetchUser();
      }
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      window.removeEventListener("auth-changed", handleAuthChanged);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return <CurrentUserContext.Provider value={state}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser() {
  return useContext(CurrentUserContext);
}
