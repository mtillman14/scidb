/**
 * Shared blocking-modal chrome (overlay + dialog box + title).
 *
 * Originally defined inline in App.tsx for the Phase 8 startup-error
 * dialog; pulled out here so ProjectBootstrapWizard can reuse the same
 * visual language instead of re-declaring its own overlay/dialog styles.
 * Callers override `border`/color on top of these for their own accent
 * (e.g. the startup-error dialog uses a red border).
 */

import type { CSSProperties } from "react";

export const overlay: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0, 0, 0, 0.75)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 10000,
};

export const dialog: CSSProperties = {
  background: "#1a1a2e",
  color: "#eee",
  border: "1px solid #2a2a4a",
  borderRadius: 6,
  padding: "20px 24px",
  maxWidth: 720,
  maxHeight: "80vh",
  overflow: "auto",
  boxShadow: "0 10px 40px rgba(0, 0, 0, 0.6)",
};

export const dialogTitle: CSSProperties = {
  fontSize: 16,
  fontWeight: 700,
  marginBottom: 12,
};
