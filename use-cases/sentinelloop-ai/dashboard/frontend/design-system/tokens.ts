import { colors } from "./colors";

export const tokens = {
  color: {
    ink: colors.ink,
    panel: colors.panel,
    panelRaised: colors.panelRaised,
    chalk: colors.chalk,
    muted: colors.muted,
    maroon: colors.maroon,
    maroonDeep: colors.maroonDeep,
    onBrand: colors.onBrand,
    signalAmber: colors.signalAmber,
    emberOrange: colors.emberOrange,
    hazardRed: colors.hazardRed,
    signalRed: colors.hazardRed,
    verifiedTeal: colors.verifiedTeal,
  },
  font: {
    heading: "'Space Grotesk', sans-serif",
    display: "'Space Grotesk', sans-serif",
    body: "'IBM Plex Sans', sans-serif",
    mono: "'IBM Plex Mono', monospace",
  },
  space: {
    1: 4,
    2: 8,
    3: 12,
    4: 16,
    5: 24,
    6: 32,
    7: 48,
  },
  radius: {
    sm: 6,
    md: 8,
  },
  riskTabWidth: 5,
} as const;
