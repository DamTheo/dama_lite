import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowLeft, Camera, Check, CircleOff, Cloud,
  CloudOff, Flame, Image, Play, Power, Square, Thermometer, WifiOff,
} from "lucide-react";
import { acknowledgeCamera, cancelShutdownConfirmation, getStatus, selectCameraForSetup, shutdownMachine, streamUrl, startTest, stopTest } from "./api";
import { Face, PowerOverlay } from "./Face";
import TouchKeyboard from "./TouchKeyboard";
import type { CameraStatus, MachineStatus, Screen, TestStatus } from "./types";

function validateExperimentFolder(value: string): string | null {
  // Même nom côté écran, SQLite et SharePoint : aucun trim silencieux.
  if (value.trim().length === 0) {
    return "Nom obligatoire : il devient le dossier SharePoint.";
  }
  if (value.length > 110) return "110 caractères maximum.";
  if (value !== value.replace(/^[ .]+|[ .]+$/g, "")) {
    return "Pas d'espace ni de point au début ou à la fin du nom.";
  }
  if (/[<>:"/\\|?*\x00-\x1f]/.test(value)
      || ["con", "prn", "aux", "nul"].includes(value.toLowerCase())) {
    return "Nom non compatible avec SharePoint.";
  }
  return null;
}

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
  if (cam.health === "fault") return "Défaut caméra";
  if (cam.health === "running") return "En cours";
  return "Connectée";
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
      className={"camera-tile " + camera.health + (selected ? " selected" : "")}
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
    led: "off" as const, health: "off" as const, active_test: null,
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
  const [confirmShutdown, setConfirmShutdown] = useState(false);
  const [shuttingDown, setShuttingDown] = useState(false);
  const [bootVisible, setBootVisible] = useState(true);
  const [frameTime, setFrameTime] = useState(Date.now());
  const [frameError, setFrameError] = useState(false);
  const frameTimer = useRef<number | null>(null);
  const videoRetryCount = useRef(0);

  function retryVideoAfterError() {
    // Les hubs USB ne doivent pas subir une boucle d'ouvertures V4L2
    // toutes les deux secondes s'ils viennent de se réinitialiser.
    videoRetryCount.current = Math.min(videoRetryCount.current + 1, 5);
    const delay = Math.min(12000, 1500 * 2 ** (videoRetryCount.current - 1));
    scheduleNextFrame(delay);
  }

  function scheduleNextFrame(delayMs: number) {
    if (frameTimer.current !== null) window.clearTimeout(frameTimer.current);
    frameTimer.current = window.setTimeout(() => {
      frameTimer.current = null;
      
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
    if (screen === "camera" || screen === "new") {
      videoRetryCount.current = 0;
      setFrameError(false);
      
      setFrameTime(Date.now());
    }
    return () => {
      if (frameTimer.current !== null) window.clearTimeout(frameTimer.current);
    };
  }, [screen, camera]);
  useEffect(() => {
    // Le clignotement des 8 LED sélectionnées s'arrête au changement de
    // page ; s'il y a une coupure réseau, le Pi l'expire au bout de 4 s.
    if (screen !== "new" && screen !== "camera") {
      void selectCameraForSetup(null).catch(() => undefined);
      return;
    }
    const ping = () => {
      void selectCameraForSetup(camera).catch(() => undefined);
    };
    ping();
    const timer = window.setInterval(ping, 1500);
    return () => window.clearInterval(timer);
  }, [screen, camera]);

  useEffect(() => {
    if (status?.shutdown_confirmation_required) {
      setConfirmStop(null);
      setKeyboard(false);
      setConfirmShutdown(true);
    }
  }, [status?.shutdown_confirmation_required]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5500);
    return () => clearTimeout(timer);
  }, [notice]);

  const cameras = status?.cameras ?? emptyCameras();
  const connectedCount = cameras.filter(cam => cam.connected).length;
  const configuredCount = cameras.filter(cam => cam.configured).length;
  const selected = cameras.find(c => c.slot === camera);
  const currentCameraTest = (status?.tests ?? []).find(
    t => t.state === "running" && t.camera_slot === camera,
  );
  const running = (status?.tests ?? []).filter(t => t.state === "running");
  const history = (status?.tests ?? []).filter(t => t.state !== "running").slice(0, 12);
  const selectedReady = Boolean(
    selected?.connected && selected.health === "available" &&
    status?.sharepoint_configured && status?.thermal.ready && online &&
    status?.power === "on",
  );
  // L'accès au nom ne nécessite pas la chauffe : seule l'action
  // "Lancer" est soumise à la sécurité des 35 °C.
  const canPrepare = Boolean(selected?.configured && !currentCameraTest && online);
  const folderNameError = validateExperimentFolder(name);
  const isShutting = shuttingDown || status?.power === "shutting";
  const title = useMemo(() => ({
    home: "ACCUEIL", menu: "QUE SOUHAITEZ-VOUS FAIRE ?",
    new: "NOUVELLE ANALYSE", cameras: "CAMÉRAS",
    camera: "RETOUR CAMÉRA " + camera, tests: "ANALYSES EN COURS",
  }[screen]), [screen, camera]);

  async function launch() {
    if (folderNameError) {
      setNotice(folderNameError);
      return;
    }
    if (!selectedReady || working) return;
    setWorking(true);
    try {
      await startTest(camera, name);
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
      setNotice("Expérience terminée : " + test.name);
      setConfirmStop(null);
      await refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Arrêt impossible");
    } finally {
      setWorking(false);
    }
  }

  async function powerOff() {
    if (working || shuttingDown) return;
    setWorking(true);
    try {
      await shutdownMachine(true);
      setShuttingDown(true);
      setConfirmShutdown(false);
      setKeyboard(false);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Extinction impossible.");
    } finally {
      setWorking(false);
    }
  }

  function cancelPowerOff() {
    setConfirmShutdown(false);
    void cancelShutdownConfirmation().catch(() => undefined);
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
            <span>{!status?.thermal.heating_enabled ? "CHAUFFE OFF" : status.thermal.heater_on ? "CHAUFFE" : status.thermal.ready ? "PRÊT" : "ATTENTE"}</span>
          </div>
          <div className="reading counts"><Camera size={17} /><strong>{connectedCount}/8</strong><span>CAMÉRAS</span></div>
          <button className="power-button" type="button" aria-label="Éteindre le Raspberry Pi proprement"
            title={status?.shutdown_available ? "Éteindre DAMA Lite" : "Extinction OS non configurée"}
            disabled={!online || isShutting || working || !status?.shutdown_available}
            onClick={() => { setKeyboard(false); setConfirmStop(null); setConfirmShutdown(true); }}>
            <Power size={20} />
          </button>
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
      {online && configuredCount > connectedCount && (
        <div className="warning-strip usb-warning"><AlertTriangle size={16} />
          USB : {connectedCount} caméra(s) accessibles sur {configuredCount} configurées.
          Vérifier le(s) hub(s) et leur alimentation.
        </div>
      )}

      <section className="machine-body">
        {screen === "home" && (
          <div className="home-layout">
            <button className="face-card" onClick={() => setScreen("menu")} aria-label="Ouvrir DAMA Lite">
              <Face />
              <h1>DAMA Lite</h1>
              <p>{status?.thermal.ready ? "Prêt pour vos expériences" : status?.thermal.heating_enabled
                ? "Préchauffage de l'enceinte" : "Chauffe désactivée · sécurité à valider"}</p>
              <span className="touch-hint">TOUCHER POUR CONTINUER</span>
            </button>
            <div className="home-stations">
              <div className="section-caption"><span>EMPLACEMENTS</span><span>{connectedCount} CAMÉRA(S) ACCESSIBLE(S)</span></div>
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
                <div className="setup-visualization">
                  <div className="tiles-grid selection">
                    {cameras.map(cam => (
                      <CameraTile camera={cam} selected={camera === cam.slot} key={cam.slot}
                        onClick={() => { setCamera(cam.slot); setKeyboard(false); }} />
                    ))}
                  </div>
                  <aside className="setup-preview" aria-label={"Aperçu de la caméra " + camera}>
                    <div className="setup-preview-heading">
                      <strong>CAM {camera}</strong><span>APERÇU DIRECT</span>
                    </div>
                    <div className="setup-preview-frame">
                      {selected?.connected ? (
                        <img key={camera} src={streamUrl(camera, frameTime)}
                          loading="eager" alt={"Position de la plaque, caméra " + camera}
                          onLoad={() => { videoRetryCount.current = 0; setFrameError(false); }}
                          onError={() => {
                            setFrameError(true);
                            retryVideoAfterError();
                          }} />
                      ) : <div className="setup-preview-empty">Caméra indisponible</div>}
                      {frameError && selected?.connected &&
                        <div className="setup-preview-warning">Reconnexion vidéo…</div>}
                    </div>
                    <small>Vérifier la position de la plaque avant de lancer.</small>
                  </aside>
                </div>
                <div className="test-entry">
                  <label htmlFor="test-name">NOM OBLIGATOIRE = DOSSIER SHAREPOINT *</label>
                  <input id="test-name" value={name} maxLength={110}
                    inputMode="none" placeholder="Ex. Ecoli_EXP_01"
                    required aria-required="true" aria-invalid={Boolean(name && folderNameError)}
                    onFocus={() => setKeyboard(true)}
                    onChange={e => setName(e.target.value)} />
                  <button className="action primary launch" disabled={!selectedReady || Boolean(folderNameError) || working}
                    onClick={() => void launch()}><Play size={20} />
                    {working ? "Préparation SharePoint..." : "Lancer l'analyse"}
                  </button>
                </div>
                <div className="hint-line">
                  {name && folderNameError ? folderNameError
                    : status?.thermal.fault ? "Défaut thermique : lancement bloqué"
                    : !status?.thermal.ready ? "Nom possible dès maintenant ; lancement uniquement dès 35 °C."
                    : !folderNameError ? "DOSSIER : DAMA-Lite / " + name
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
                    <img key={camera} src={streamUrl(camera, frameTime)}
                      loading="eager" alt={"Flux direct de la caméra " + camera}
                      onLoad={() => { videoRetryCount.current = 0; setFrameError(false); }}
                      onError={() => {
                        setFrameError(true);
                        retryVideoAfterError();
                      }} />
                  ) : <div className="empty-preview"><CircleOff size={36} /> Caméra absente</div>}
                  {frameError && <div className="preview-error">Aperçu momentanément indisponible · nouvel essai automatique</div>}
                </div>
                <aside className="camera-info">
                  <strong>CAM {camera}</strong>
                  <span className={"state-mark " + selected?.health}>{selected ? cameraLabel(selected) : "—"}</span>
                  <p>Flux MJPEG continu sans réencodage. Photographies PNG haute résolution prioritaires.</p>
                  <button className="action" disabled={!selected?.connected}
                    onClick={() => {
                      if (frameTimer.current !== null) window.clearTimeout(frameTimer.current);
                      frameTimer.current = null;
                      
                      videoRetryCount.current = 0;
                      setFrameTime(Date.now());
                      setFrameError(false);
                    }}>Reconnecter</button>
                  {selected?.led === "fault" && selected.connected
                    && !selected.active_test && !status?.thermal.fault &&
                    <button className="action" disabled={working}
                      onClick={() => void clearCameraFault(camera)}>
                      <Check size={18} /> Acquitter le défaut
                    </button>}
                  {currentCameraTest ? (
                    <button className="action danger" disabled={working}
                      onClick={() => setConfirmStop(currentCameraTest)}>
                      <Square size={18} /> Terminer l'expérience
                    </button>
                  ) : (
                    <button className="action primary" disabled={!canPrepare}
                      onClick={() => { setName(""); setKeyboard(false); setScreen("new"); }}>
                      <Play size={18} /> Lancer une analyse
                    </button>
                  )}
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
                    <button className="stop-btn" onClick={() => setConfirmStop(test)}><Square size={16} /> Terminer</button>
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
      {confirmShutdown && <div className="modal-backdrop"><div className="confirm-card shutdown-card"
        role="dialog" aria-modal="true" aria-label="Confirmer l'extinction de DAMA Lite">
        <Power size={29} /><h2>Éteindre DAMA Lite ?</h2>
        {running.length > 0 ? (
          <>
            <p><strong>{running.length} expérience(s) en cours.</strong> Confirmer terminera toutes les sessions et arrêtera les acquisitions.</p>
            <p className="shutdown-names">{running.map(t => t.name).join(" · ")}</p>
          </>
        ) : <p>Aucune expérience en cours. Le Raspberry Pi s'éteindra proprement.</p>}
        {(status?.pending_uploads ?? 0) > 0 && <p>
          {status?.pending_uploads} photo(s) en attente de SharePoint :
          elles resteront sur le Pi pour synchronisation au prochain démarrage.
        </p>}
        <p>La chauffe est coupée en priorité ; extinction Linux après l'animation.</p>
        <button className="action danger" disabled={working} onClick={() => void powerOff()}>
          <Power size={18} /> {working ? "Préparation de l'arrêt…" : "Confirmer et éteindre"}
        </button>
        <button className="action" disabled={working} onClick={cancelPowerOff}>Annuler, rester allumé</button>
      </div></div>}
      {confirmStop && !confirmShutdown && <div className="modal-backdrop"><div className="confirm-card">
        <AlertTriangle size={28} /><h2>Terminer l'expérience ?</h2>
        <p>{confirmStop.name} — caméra {confirmStop.camera_slot}. Les nouvelles acquisitions s'arrêtent ; les photos déjà acquises seront conservées et transférées sur SharePoint.</p>
        <button className="action danger" disabled={working} onClick={() => void stopCurrent(confirmStop)}>Confirmer la fin</button>
        <button className="action" onClick={() => setConfirmStop(null)}>Poursuivre l'expérience</button>
      </div></div>}
      {notice && <div className="toast" role="status"><AlertTriangle size={17} />{notice}<button onClick={() => setNotice(null)} aria-label="Fermer"><Check size={17} /></button></div>}
      {bootVisible && !isShutting && <PowerOverlay mode="booting" />}
      {isShutting && <PowerOverlay mode="shutting" />}
      {status?.power === "shutdown_failed" && <div className="blocking-alarm"><Flame /> Arrêt OS impossible : chauffage coupé. Intervention requise.</div>}
    </main>
  );
}
