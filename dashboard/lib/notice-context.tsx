"use client";

import { createContext, useContext, useState, useCallback } from "react";

type NoticeContextValue = {
  notice: string;
  error: string;
  busy: boolean;
  setNotice: (value: string) => void;
  setError: (value: string) => void;
  runAction: (action: () => Promise<unknown>, successMsg: string) => Promise<void>;
};

const NoticeContext = createContext<NoticeContextValue | null>(null);

export function NoticeProvider({ children }: { children: React.ReactNode }) {
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const runAction = useCallback(async (action: () => Promise<unknown>, successMsg: string) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(successMsg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <NoticeContext.Provider value={{ notice, error, busy, setNotice, setError, runAction }}>
      {children}
    </NoticeContext.Provider>
  );
}

export function useNotice(): NoticeContextValue {
  const ctx = useContext(NoticeContext);
  if (!ctx) throw new Error("useNotice must be used within NoticeProvider");
  return ctx;
}
