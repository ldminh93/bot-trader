"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
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
    if (requested.current) return;
    requested.current = true;
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
  }, []);

  return <CurrentUserContext.Provider value={state}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser() {
  return useContext(CurrentUserContext);
}
