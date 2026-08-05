#!/usr/bin/env bash
# GameCore — desktop launcher.
# Starts the GameCore services (backend + kiosk UI) from the KDE/desktop
# session, e.g. after returning to the desktop. Installed as a clickable
# .desktop entry by install/arch.sh.
#
# is-active is a status query (no root needed); only `start` is elevated,
# via the NOPASSWD sudoers rule created by the installer.
set -u

SERVICES=("gamecore-backend.service" "gamecore-ui.service")

for SERVICE in "${SERVICES[@]}"; do
  if systemctl is-active --quiet "$SERVICE"; then
    echo "🟢 $SERVICE est déjà en cours d'exécution."
  else
    echo "🔴 $SERVICE est arrêté. Démarrage en cours..."
    if sudo -n systemctl start "$SERVICE" 2>/dev/null && systemctl is-active --quiet "$SERVICE"; then
      echo "✅ $SERVICE a été démarré avec succès."
    else
      echo "❌ Échec du démarrage de $SERVICE."
    fi
  fi
done

# Leave the window open a moment so the result is readable when clicked.
sleep 3
