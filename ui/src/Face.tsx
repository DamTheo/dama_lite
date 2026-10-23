import type { ReactNode } from "react";

export function Face({ sleeping = false }: { sleeping?: boolean }) {
  return (
    <div className={"dama-face" + (sleeping ? " is-sleeping" : "")} aria-hidden="true">
      <div className="face-eyes"><span className="face-eye" /><span className="face-eye" /></div>
      <svg className="face-smile" viewBox="0 0 100 36">
        <path d="M 12 8 Q 50 46 88 8" />
      </svg>
    </div>
  );
}

export function PowerOverlay({ mode }: { mode: "booting" | "shutting" }): ReactNode {
  return (
    <div className={"power-overlay " + mode} role="status" aria-live="polite">
      <div className="morph-stage">
        <div className="morph-logo"><span className="brand-monogram">D<span>.</span></span></div>
        <div className="morph-face"><Face /></div>
      </div>
      <p className="morph-caption">{mode === "booting" ? "Démarrage DAMA Lite" : "Extinction DAMA Lite"}</p>
      {mode === "booting" && <p className="morph-subtitle">INCUBATEUR · DAMOCLES DX</p>}
    </div>
  );
}
