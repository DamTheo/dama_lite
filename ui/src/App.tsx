import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowLeft, Camera, Check, CircleOff, Cloud,
  CloudOff, Flame, Image, Play, Square, Thermometer, WifiOff,
} from "lucide-react";
import { acknowledgeCamera, getStatus, previewUrl, startTest, stopTest } from "./api";
import { Face, PowerOverlay } from "./Face";
import TouchKeyboard from "./TouchKeyboard";
import type { CameraStatus, MachineStatus, Screen, TestStatus } from "./types";

const LABELS = {
  available: "Disponible",
  running: "En cours",
  fault: "Défaut",
  off: "Indisponible",
} as const;

// L'état LED dépend aussi du préchauffage. Une caméra raccordée reste
// consultable même si la température est inférieure à 35 °C.
function cameraLabel(cam: CameraStatus): string {
  if (!cam.configured) return "Non configurée";
  if (!cam.connected) return "Déconnectée";
  if (cam.led === "off") return "Connectée";
  return LABELS[cam.led];
}

function formatTemp(value: number | null): string {
  return value === null ? "—" : value.toLocaleString("fr-FR", {
    minimumFractionDigits: 1, maximumFractionDigits: 1,
  }) + " °C";
}

function formatTime(seconds: number | null): string {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60), s = Math.round(seconds % 60);
  return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
}

function CameraTile({
  camera, selected, onClick,
}: {
  camera: CameraStatus; selected?: boolean; onClick: () => void;
}) {
  return (
    <button
      className={"camera-tile " + camera.led + (selected ? " selected" : "")}
      onClick={onClick}
      aria-label={"Caméra " + camera.slot + " : " + cameraLabel(camera)}
      type="button"
    >
      <span className="camera-tile-icon"><Camera size={20} /></span>
      <span className="camera-tile-label">CAM {camera.slot}</span>
      <span className="camera-tile-state"><i />{cameraLabel(camera)}</span>
    </button>
  );
}

function emptyCameras(): CameraStatus[] {
  return Array.from({ length: 8 }, (_, index) => ({
    slot: index + 1, configured: false, connected: false,
    led: "off" as const, active_test: null,
  }));
}

export default function App() {
  const [status, setStatus] = useState<MachineStatus | null>(null);
  const [online, setOnline] = useState(false);
  const [screen, setScreen] = useState<Screen>("home");
  const [camera, setCamera] = useState(1);
  const [name, setName] = useState("");
  const [keyboard, setKeyboard] = useState(false);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState<TestStatus | null>(null);
  const [bootVisible, setBootVisible] = useState(true);
  const [frameTime, setFrameTime] = useState(Date.now());
  const [frameError, setFrameError] = useState(false);
  const [frameLoading, setFrameLoading] = useState(false);
  const frameTimer = useRef<number | null>(null);

  function scheduleNextFrame(delayMs: number) {
    if (frameTimer.current !== null) window.clearTimeout(frameTimer.current);
    frameTimer.current = window.setTimeout(() => {
      frameTimer.current = null;
      setFrameLoading(true);
      setFrameTime(Date.now());
    }, delayMs);
  }

  async function refresh() {
    try {
      const next = await getStatus();
      setStatus(next);
      setOnline(true);
    } catch {
      setOnline(false);
      setStatus(null);
    }
  }
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 1000);
    const boot = window.setTimeout(() => setBootVisible(false), 4400);
    return () => { clearInterval(timer); clearTimeout(boot); };
  }, []);
  useEffect(() => {
    if (frameTimer.current !== null) {
      window.clearTimeout(frameTimer.current);
      frameTimer.current = null;
    }
    if (screen === "camera") {
      setFrameError(false);
      setFrameLoading(true);
      setFrameTime(Date.now());
    }
    return () => {
      if (frameTimer.current !== null) window.clearTimeout(frameTimer.current);
    };
  }, [screen, camera]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5500);
    return () => clearTimeout(timer);
  }, [notice]);

  const cameras = status?.cameras ?? emptyCameras();
  const selected = cameras.find(c => c.slot === camera);
  const running = (status?.tests ?? []).filter(t => t.state === "running");
  const history = (status?.tests ?? []).filter(t => t.state !== "running").slice(0, 12);
  const selectedReady = Boolean(
    selected?.led === "available" && status?.sharepoint_configured
    && status?.thermal.ready && online,
  );
  const isShutting = status?.power === "shutting";
  const title = useMemo(() => ({
    home: "ACCUEIL", menu: "QUE SOUHAITEZ-VOUS FAIRE ?",
    new: "NOUVELLE ANALYSE", cameras: "CAMÉRAS",
    camera: "RETOUR CAMÉRA " + camera, tests: "ANALYSES EN COURS",
  }[screen]), [screen, camera]);

  async function launch() {
    if (!name.trim() || !selectedReady || working) return;
    setWorking(true);
    try {
      await startTest(camera, name.trim());
      setName("");
      setKeyboard(false);
      setScreen("tests");
      setNotice("Analyse lancée sur la caméra " + camera + ".");
      await refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Démarrage impossible");
    } finally {
      setWorking(false);
    }
  }

  async function stopCurrent(test: TestStatus) {
    setWorking(true);
    try {
      await stopTest(test.id);
      setNotice("Analyse arrêtée : " + test.name);
      setConfirmStop(null);
      await refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Arrêt impossible");
    } finally {
      setWorking(false);
    }
  }

  async function clearCameraFault(slot: number) {
    setWorking(true);
    try {
      await acknowledgeCamera(slot);
      setNotice("Défaut acquitté sur la caméra " + slot + ".");
      await refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Acquittement impossible");
    } finally {
      setWorking(false);
    }
  }

  function goBack() {
    if (keyboard) { setKeyboard(false); return; }
    setScreen(screen === "camera" ? "cameras" : "home");
  }

  return (
    <main className="machine-root">
      <header className="machine-header">
        <div className="brand">
          <img className="brand-symbol" src="/damocles-logo.svg" alt="Logo DAMOCLES Dx" />
          <div><strong>DAMA<span className="brand-accent">.</span> <small>LITE</small></strong>
            <span className="brand-sub">by DAMOCLES Dx</span></div>
        </div>
        <div className="machine-readings">
          <div className={"reading " + (status?.thermal.ready ? "ok" : "warm")}>
            <Thermometer size={17} />
            <strong>{formatTemp(status?.thermal.temperature_c ?? null)}</strong>
            <span>{status?.thermal.heater_on ? "CHAUFFE" : status?.thermal.ready ? "PRÊT" : "ATTENTE"}</span>
          </div>
          <div className="reading counts"><Camera size={17} /><strong>{running.length}/8</strong><span>ACTIVES</span></div>
        </div>
      </header>

      {status?.thermal.cpu_warning && (
        <div className="warning-strip"><AlertTriangle size={16} />
          Attention, j'ai chaud : CPU {formatTemp(status.thermal.cpu_temperature_c)} (alerte dès 65 °C)
        </div>
      )}
      {status?.thermal.fault && (
        <div className="warning-strip critical"><AlertTriangle size={16} />
          Défaut thermique : {status.thermal.fault} · chauffage désactivé
        </div>
      )}
      {!online && <div className="warning-strip critical"><WifiOff size={16} /> Contrôleur indisponible : commandes désactivées.</div>}

      <section className="machine-body">
        {screen === "home" && (
          <div className="home-layout">
            <button className="face-card" onClick={() => setScreen("menu")} aria-label="Ouvrir DAMA Lite">
              <Face />
              <h1>DAMA Lite</h1>
              <p>{status?.thermal.ready ? "Prêt pour vos expériences" : status?.thermal.heating_enabled
                ? "Préchauffage de l'enceinte" : "En attente de configuration"}</p>
              <span className="touch-hint">TOUCHER POUR CONTINUER</span>
            </button>
            <div className="home-stations">
              <div className="section-caption"><span>EMPLACEMENTS</span><span>{running.length} EN COURS</span></div>
              <div className="tiles-grid">
                {cameras.map(cam => (
                  <CameraTile camera={cam} key={cam.slot} onClick={() => {
                    setCamera(cam.slot);
                    setScreen(cam.connected ? "camera" : "cameras");
                  }} />
                ))}
              </div>
              <div className="home-footer">
                <span><i className="dot green" /> LIBRE</span>
                <span><i className="dot yellow" /> EN COURS</span>
                <span><i className="dot red" /> DÉFAUT</span>
              </div>
            </div>
          </div>
        )}

        {screen !== "home" && (
          <div className="page">
            <div className="page-heading">
              <button className="icon-button back" onClick={goBack} aria-label="Retour"><ArrowLeft /></button>
              <span>{title}</span>
              <span className="page-counter">{status?.thermal.ready ? "ENCEINTE PRÊTE" : "ENCEINTE EN ATTENTE"}</span>
            </div>

            {screen === "menu" && (
              <div className="menu-screen">
                <Face />
                <div className="menu-options">
                  <button className="action primary" onClick={() => setScreen("new")}><Play /> Lancer une analyse <span>→</span></button>
                  <button className="action" onClick={() => setScreen("cameras")}><Camera /> Visualiser une caméra <span>→</span></button>
                  <button className="action secondary" onClick={() => setScreen("tests")}><Image /> Suivre les analyses <span>{running.length}</span></button>
                </div>
              </div>
            )}

            {screen === "new" && (
              <div className="new-screen">
                <div className="section-caption"><span>CHOISIR UNE CAMÉRA</span><span>UNE CAMÉRA = UN TEST</span></div>
                <div className="tiles-grid selection">
                  {cameras.map(cam => (
                    <CameraTile camera={cam} selected={camera === cam.slot} key={cam.slot}
                      onClick={() => { setCamera(cam.slot); setKeyboard(false); }} />
                  ))}
                </div>
                <div className="test-entry">
                  <label htmlFor="test-name">NOM DE L'EXPÉRIENCE</label>
                  <input id="test-name" value={name} maxLength={110}
                    inputMode="none" placeholder="Ex. Ecoli_EXP_01"
                    onFocus={() => setKeyboard(true)}
                    onChange={e => setName(e.target.value)} />
                  <button className="action primary launch" disabled={!selectedReady || !name.trim() || working}
                    onClick={() => void launch()}><Play size={20} />
                    {working ? "Préparation SharePoint..." : "Lancer l'analyse"}
                  </button>
                </div>
                <div className="hint-line">
                  {status?.thermal.fault ? "Défaut thermique : lancement bloqué"
                    : !status?.thermal.ready ? "Le lancement nécessite une enceinte à 35 °C minimum."
                      : !status.sharepoint_configured ? "SharePoint non configuré."
                        : !selected?.connected ? "Caméra non connectée."
                          : selected?.led !== "available" ? "Cette caméra n'est pas disponible."
                            : "Première photo immédiate, puis toutes les 5 minutes."}
                </div>
              </div>
            )}

            {screen === "cameras" && (
              <div className="cameras-screen">
                <p className="section-caption">SÉLECTIONNER UN EMPLACEMENT POUR VOIR SON IMAGE</p>
                <div className="tiles-grid">
                  {cameras.map(cam => (
                    <CameraTile camera={cam} key={cam.slot}
                      onClick={() => { setCamera(cam.slot); setScreen("camera"); }} />
                  ))}
                </div>
              </div>
            )}

            {screen === "camera" && (
              <div className="camera-screen">
                <div className="preview-frame">
                  {selected?.connected ? (
                    <img src={previewUrl(camera, frameTime)} alt={"Image de la caméra " + camera}
                      onLoad={() => {
                        setFrameError(false);
                        setFrameLoading(false);
                        scheduleNextFrame(1500);
                      }}
                      onError={() => {
                        setFrameError(true);
                        setFrameLoading(false);
                        scheduleNextFrame(4500);
                      }} />
                  ) : <div className="empty-preview"><CircleOff size={36} /> Caméra absente</div>}
                  {frameError && <div className="preview-error">Aperçu momentanément indisponible · nouvel essai automatique</div>}
                </div>
                <aside className="camera-info">
                  <strong>CAM {camera}</strong>
                  <span className={"state-mark " + selected?.led}>{selected ? cameraLabel(selected) : "—"}</span>
                  <p>Aperçu actualisé après réception de la précédente image. Les acquisitions des tests restent prioritaires.</p>
                  <button className="action" disabled={!selected?.connected || frameLoading}
                    onClick={() => {
                      if (frameTimer.current !== null) window.clearTimeout(frameTimer.current);
                      frameTimer.current = null;
                      setFrameLoading(true);
                      setFrameTime(Date.now());
                      setFrameError(false);
                    }}>Actualiser</button>
                  {selected?.led === "fault" && selected.connected
                    && !selected.active_test && !status?.thermal.fault &&
                    <button className="action" disabled={working}
                      onClick={() => void clearCameraFault(camera)}>
                      <Check size={18} /> Acquitter le défaut
                    </button>}
                  <button className="action primary" disabled={!selectedReady} onClick={() => setScreen("new")}>
                    <Play size={18} /> Nouveau test
                  </button>
                </aside>
              </div>
            )}

            {screen === "tests" && (
              <div className="tests-screen">
                {running.length === 0 ? <div className="empty-tests"><Image size={35} />
                  Aucune analyse en cours
                  <button className="action primary" onClick={() => setScreen("new")}>Nouvelle analyse</button>
                </div> : running.map(test => (
                  <div className="test-row" key={test.id}>
                    <span className="test-cam">CAM {test.camera_slot}</span>
                    <div className="test-main"><strong>{test.name}</strong>
                      <small>{test.images_count} photo(s) · {test.pending_uploads} en attente SharePoint
                        {test.upload_errors > 0 ? " · ERREUR DE SYNCHRONISATION" : ""}</small></div>
                    <div className="test-next"><small>PROCHAINE PHOTO</small><strong>{formatTime(test.next_photo_seconds)}</strong></div>
                    <button className="stop-btn" onClick={() => setConfirmStop(test)}><Square size={16} /> Arrêter</button>
                  </div>
                ))}
                {history.length > 0 && <div className="history-panel">
                  <h3>HISTORIQUE RÉCENT</h3>
                  {history.map(test => (
                    <div className="history-row" key={test.id}>
                      <strong>CAM {test.camera_slot}</strong>
                      <span>{test.name}</span>
                      <small className={test.state === "fault" || test.state === "interrupted" ? "history-fault" : ""}>
                        {test.state === "stopped" ? "Arrêté" :
                          test.state === "fault" ? "Défaut" :
                            test.state === "interrupted" ? "Interrompu" : test.state}
                      </small>
                      <small>{test.images_count} photo(s) · {test.pending_uploads} en attente</small>
                      {test.error && <p>{test.error}{test.acknowledged ? " · acquitté" : ""}</p>}
                    </div>
                  ))}
                </div>}
              </div>
            )}
          </div>
        )}
      </section>
      <footer className="machine-footer">
        <span><span className={"online-dot " + (online ? "up" : "down")} />
          {online ? "CONTRÔLEUR CONNECTÉ" : "CONNEXION INTERROMPUE"}</span>
        <span>{status?.sharepoint_configured ? <><Cloud size={13} /> SHAREPOINT CONFIGURÉ</> :
          <><CloudOff size={13} /> SHAREPOINT NON CONFIGURÉ</>}</span>
        <span>37 °C · 5 MIN · 8 CAMÉRAS</span>
      </footer>

      {keyboard && screen === "new" && <TouchKeyboard value={name} onChange={setName} onDone={() => setKeyboard(false)} />}
      {confirmStop && <div className="modal-backdrop"><div className="confirm-card">
        <AlertTriangle size={28} /><h2>Arrêter l'analyse ?</h2>
        <p>{confirmStop.name} — caméra {confirmStop.camera_slot}. Les photos déjà acquises seront conservées et transférées.</p>
        <button className="action danger" disabled={working} onClick={() => void stopCurrent(confirmStop)}>Confirmer l'arrêt</button>
        <button className="action" onClick={() => setConfirmStop(null)}>Continuer l'analyse</button>
      </div></div>}
      {notice && <div className="toast" role="status"><AlertTriangle size={17} />{notice}<button onClick={() => setNotice(null)} aria-label="Fermer"><Check size={17} /></button></div>}
      {bootVisible && !isShutting && <PowerOverlay mode="booting" />}
      {isShutting && <PowerOverlay mode="shutting" />}
      {status?.power === "shutdown_failed" && <div className="blocking-alarm"><Flame /> Arrêt OS impossible : chauffage coupé. Intervention requise.</div>}
    </main>
  );
}
