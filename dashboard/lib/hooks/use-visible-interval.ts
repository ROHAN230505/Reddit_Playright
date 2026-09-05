"use client";

import { useEffect, useRef } from "react";

/**
 * setInterval that skips ticks while the document is hidden and fires once
 * when the tab becomes visible again. Pass `null` to disable.
 */
export function useVisibleInterval(callback: () => void, ms: number | null) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    if (ms == null || ms <= 0) return;

    const tick = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      callbackRef.current();
    };

    const timer = window.setInterval(tick, ms);
    const onVisibility = () => {
      if (document.visibilityState === "visible") callbackRef.current();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [ms]);
}
