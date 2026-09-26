import { useEffect, useRef, useState } from "react";

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** Animate from 0 to `target` (ease-out) whenever target changes. */
export function useCountUp(target: number | null, durationMs = 900): number | null {
  const reduced = usePrefersReducedMotion();
  const [v, setV] = useState<number | null>(target);
  useEffect(() => {
    if (target === null || reduced) {
      setV(target);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / durationMs);
      setV(target * (1 - (1 - p) ** 3));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs, reduced]);
  return v;
}

/** Track an element's content width for responsive SVG charts. */
export function useWidth<T extends HTMLElement>(fallback = 600): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setW(Math.max(200, Math.floor(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Read/write a localStorage string; storage failures fall back to in-memory state. */
export function useStoredState<T extends string>(key: string, initial: T, valid: readonly T[]): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const s = localStorage.getItem(key) as T | null;
      return s && valid.includes(s) ? s : initial;
    } catch {
      return initial;
    }
  });
  const set = (next: T) => {
    setV(next);
    try {
      localStorage.setItem(key, next);
    } catch {
      /* private mode: keep in memory only */
    }
  };
  return [v, set];
}
