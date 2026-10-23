import { Check, Delete, Space } from "lucide-react";

const ROWS = [
  "1234567890",
  "AZERTYUIOP",
  "QSDFGHJKLM",
  "WXCVBN-_." ,
];

export default function TouchKeyboard({
  value, onChange, onDone,
}: {
  value: string;
  onChange: (next: string) => void;
  onDone: () => void;
}) {
  function append(key: string) {
    if (value.length < 110) onChange(value + key);
  }
  return (
    <div className="keyboard-overlay" role="dialog" aria-label="Clavier de nom de test">
      <div className="keyboard-top">
        <span>Nom du test</span>
        <strong>{value || "…"}</strong>
        <button className="key key-action" onClick={onDone} aria-label="Valider le nom"><Check size={18} /> OK</button>
      </div>
      <div className="keyboard-rows">
        {ROWS.map((row) => (
          <div className="keyboard-row" key={row}>
            {Array.from(row).map((key, index) => (
              <button className="key" key={key + index} onClick={() => append(key)}>{key}</button>
            ))}
          </div>
        ))}
        <div className="keyboard-row">
          <button className="key key-wide" onClick={() => append(" ")} aria-label="Espace"><Space size={17} /> Espace</button>
          <button className="key key-wide" onClick={() => onChange(value.slice(0, -1))} aria-label="Effacer"><Delete size={18} /> Effacer</button>
        </div>
      </div>
    </div>
  );
}
