#!/bin/sh
# Kiosque DAMA Lite : n'ouvrir Chromium qu'une fois le service HTTP disponible.
# Compatible avec autologin LightDM sur l'écran tactile DSI 800x480.
# N'agit ni sur les résistances, ni sur les GPIO, ni sur SharePoint.
set -eu

URL="http://127.0.0.1:8765"
CHROMIUM="/usr/bin/chromium"

if [ ! -x "$CHROMIUM" ]; then
  echo "DAMA Lite : Chromium est absent" >&2
  exit 1
fi
command -v curl >/dev/null 2>&1 || {
  echo "DAMA Lite : curl absent" >&2
  exit 1
}

# Le service systemd peut démarrer après la session graphique.
until curl --silent --fail --max-time 2 "$URL/api/health" >/dev/null; do
  sleep 2
done

# Aucune commande privilégiée, aucune fermeture de session automatique.
exec "$CHROMIUM" \
  --kiosk \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --overscroll-history-navigation=0 \
  "$URL"
