import { useEffect, useState } from "react";

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** How long ago `iso` was, such as "5 minutes ago", or "just now" within the last minute. */
export function ago(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((Date.parse(iso) - now) / 1000);
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) {
      return relative.format(Math.round(seconds / size), unit);
    }
  }
  return "just now";
}

/** A span of seconds, such as "45s" or "3m 5s". */
export function duration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return minutes > 0 ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
}

/** The span between two times, to a tenth of a second under ten seconds, such as "0.2s", "41s", or "1m 50s". */
export function between(from: string, to: string): string {
  const seconds = Math.max(0, (Date.parse(to) - Date.parse(from)) / 1000);
  return seconds < 10
    ? `${seconds.toFixed(1)}s`
    : duration(Math.round(seconds));
}

/** Now, ticking every second while `ticking`, for elapsed times that count up. */
export function useNow(ticking = true): number {
  const [now, setNow] = useState(Date.now);

  useEffect(() => {
    if (!ticking) {
      return;
    }
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [ticking]);

  return now;
}

/** How long since `iso` until now, counting up each second, such as "2m 14s". */
export function useElapsed(iso: string): string {
  const now = useNow();
  return duration(Math.max(0, Math.round((now - Date.parse(iso)) / 1000)));
}
