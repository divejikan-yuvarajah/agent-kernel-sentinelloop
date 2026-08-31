import type { SVGProps } from "react";

const PATHS = {
  dashboard: "M4 4h7v7H4V4zm9 0h7v4h-7V4zM4 13h7v7H4v-7zm9 6h7v4h-7v-4zm0-6h7v4h-7v-4z",
  emergency: "M12 3l9 16H3L12 3zm0 6v4m0 3h.01",
  incidents: "M4 6h16M4 12h16M4 18h10",
  followup: "M5 12l5 5L20 7",
  evidence: "M4 5h16v14H4V5zm4 4l3 4 2-2 3 4H8l3-4z",
  slack: "M8 3v3H5v2h3v3h2V8h3V6H10V3H8zm6 8v3h-3v2h3v3h2v-3h3v-2h-3v-3h-2z",
  duplicates: "M8 7h12v12H8V7zM4 3h12v2H6v10H4V3z",
  officers: "M12 12a4 4 0 100-8 4 4 0 000 8zm-8 9a8 8 0 0116 0",
  people: "M16 11a3 3 0 100-6 3 3 0 000 6zM8 13a3 3 0 100-6 3 3 0 000 6zm8 2a5 5 0 015 5H11a5 5 0 015-5zM8 15a5 5 0 00-5 5h8",
  analytics: "M4 19V9m6 10V5m6 14v-7m6 7H2",
  forecast: "M5 19l5-6 4 3 5-8",
  telegram: "M21 5L3 12l7 2 2 7 3-5 4 3 2-14z",
  reports: "M7 3h8l5 5v13H7V3zm8 0v5h5M9 13h6M9 17h4",
  knowledge: "M4 5h7a3 3 0 013 3v11a3 3 0 00-3-3H4V5zm9 0h7v11h-7a3 3 0 00-3 3V8a3 3 0 013-3z",
  alerts: "M12 3a7 7 0 017 7v4l2 3H3l2-3V10a7 7 0 017-7zm0 18a3 3 0 01-3-3h6a3 3 0 01-3 3z",
  safety: "M12 3l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V7l8-4z",
  review: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  settings: "M12 8a4 4 0 100 8 4 4 0 000-8zm8.5 4a8.5 8.5 0 00-.2-1.8l2-1.5-2-3.5-2.4.8a8.6 8.6 0 00-1.6-1L15.8 2h-4l-.5 2.5a8.6 8.6 0 00-1.6 1L7.3 4.7l-2 3.5 2 1.5A8.5 8.5 0 006.5 12c0 .6.1 1.2.2 1.8l-2 1.5 2 3.5 2.4-.8a8.6 8.6 0 001.6 1l.5 2.5h4l.5-2.5a8.6 8.6 0 001.6-1l2.4.8 2-3.5-2-1.5c.1-.6.2-1.2.2-1.8z",
  search: "M11 4a7 7 0 015.6 11.2L21 20l-1 1-4.4-4.4A7 7 0 1111 4zm0 2a5 5 0 100 10 5 5 0 000-10z",
  sun: "M12 4V2m0 20v-2M4 12H2m20 0h-2M5.6 5.6L4.2 4.2m15.6 15.6l-1.4-1.4M18.4 5.6l1.4-1.4M5.6 18.4l-1.4 1.4M12 8a4 4 0 100 8 4 4 0 000-8z",
  moon: "M17 14a7 7 0 01-7-9 7 7 0 108.9 8.9A7 7 0 0117 14z",
  bell: "M12 4a6 6 0 016 6v3l2 3H4l2-3V10a6 6 0 016-6zm-2 15a2 2 0 004 0",
  menu: "M4 7h16M4 12h16M4 17h16",
  collapse: "M15 6l-6 6 6 6",
  expand: "M9 6l6 6-6 6",
  close: "M6 6l12 12M18 6L6 18",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zm-7 9a7 7 0 0114 0",
  logout: "M10 4H5v16h5M14 8l4 4-4 4M9 12h9",
  spark: "M12 2l1.6 6.4L20 10l-6.4 1.6L12 18l-1.6-6.4L4 10l6.4-1.6L12 2z",
  trendUp: "M5 16l6-6 3 3 5-7",
  image: "M4 5h16v14H4V5zm3 10l3-4 2 2 3-4 3 6H7z",
  clock: "M12 7v5l3 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z",
  check: "M5 12l5 5L20 7",
  retry: "M4 12a8 8 0 0113.7-5.7L20 8M20 4v4h-4M20 12a8 8 0 01-13.7 5.7L4 16M4 20v-4h4",
  export: "M12 4v10m0-10l-4 4m4-4l4 4M5 16v3h14v-3",
  chevron: "M8 10l4 4 4-4",
} as const;

export type IconName = keyof typeof PATHS;

type Props = SVGProps<SVGSVGElement> & {
  name: IconName;
};

export function Icon({ name, className = "", ...rest }: Props) {
  const strokeIcons = new Set<IconName>([
    "emergency",
    "incidents",
    "followup",
    "analytics",
    "forecast",
    "reports",
    "alerts",
    "review",
    "search",
    "sun",
    "moon",
    "bell",
    "menu",
    "collapse",
    "expand",
    "close",
    "user",
    "logout",
    "trendUp",
    "clock",
    "check",
    "retry",
    "export",
    "chevron",
  ]);
  const stroke = strokeIcons.has(name);
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      aria-hidden="true"
      className={`ds-icon ${className}`.trim()}
      fill={stroke ? "none" : "currentColor"}
      stroke={stroke ? "currentColor" : "none"}
      strokeWidth={stroke ? 1.75 : undefined}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
