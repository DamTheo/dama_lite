// Cadrage plein cadre du MJPEG sur le tactile Raspberry Pi 7" (800x480).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const cssPath = resolve(dirname(fileURLToPath(import.meta.url)), "../src/styles.css");
const css = readFileSync(cssPath, "utf8");
for (const selector of [".preview-frame img", ".setup-preview-frame img"]) {
  const match = css.split(selector + " {")[1]?.split("}")[0];
  if (!match) throw new Error("Aucune declaration pour " + selector);
  for (const declaration of [
    "position: absolute", "inset: 0", "width: 100%", "height: 100%",
    "object-fit: contain", "object-position: center"
  ]) {
    if (!match.includes(declaration)) {
      throw new Error("Rognage potentiel sur " + selector + " : " + declaration);
    }
  }
}
console.log("Verification CSS : bas de l'image conserve dans les deux apercus.");
