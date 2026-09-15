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

let cachedUser: CurrentUser | null = null;
let cachedFetchFailed = false;

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CurrentUserState>({
    user: cachedUser,
    isStaff: cachedUser?.is_staff ?? false,
    loading: cachedUser === null && !cachedFetchFailed,
  });
  const requested = useRef(cachedUser !== null || cachedFetchFailed);

  useEffect(() => {
    function fetchUser() {
      requested.current = true;
      setState((s) => ({ ...s, loading: true }));
      api
        .me()
        .then((currentUser) => {
          cachedUser = currentUser;
          setState({ user: currentUser, isStaff: currentUser.is_staff, loading: false });
        })
        .catch(() => {
          cachedFetchFailed = true;
          setState({ user: null, isStaff: false, loading: false });
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
    return () => window.removeEventListener("auth-changed", handleAuthChanged);
  }, []);

  return <CurrentUserContext.Provider value={state}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser() {
  return useContext(CurrentUserContext);
}
