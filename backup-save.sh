#!/bin/bash

# Dossier de destination
BACKUP_DIR="$HOME/Desktop/Backup_Saves_$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

echo "--- 🚀 Lancement de la sauvegarde globale ---"

# 1. Azahar (3DS)
echo "[>] Azahar..."
mkdir -p "$BACKUP_DIR/Azahar"
cp -r ~/.var/app/org.azahar_emu.Azahar/data/azahar-emu/nand "$BACKUP_DIR/Azahar/"
cp -r ~/.var/app/org.azahar_emu.Azahar/data/azahar-emu/sdmc "$BACKUP_DIR/Azahar/"

# 2. RPCS3 (PS3)
echo "[>] RPCS3..."
mkdir -p "$BACKUP_DIR/RPCS3"
cp -r ~/.var/app/net.rpcs3.RPCS3/config/rpcs3/dev_hdd0/home/00000001/savedata "$BACKUP_DIR/RPCS3/"

# 3. PCSX2 (PS2)
echo "[>] PCSX2..."
cp -r ~/.var/app/net.pcsx2.PCSX2/config/PCSX2/memcards "$BACKUP_DIR/PCSX2"

# 4. Dolphin (GC/Wii)
echo "[>] Dolphin..."
mkdir -p "$BACKUP_DIR/Dolphin"
cp -r ~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/GC "$BACKUP_DIR/Dolphin/"
[ -d ~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Wii/title ] && cp -r ~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Wii/title "$BACKUP_DIR/Dolphin/"

# 5. melonDS (DS)
echo "[>] melonDS..."
[ -d ~/.var/app/net.kuribo64.melonDS/data/melonDS ] && cp -r ~/.var/app/net.kuribo64.melonDS/data/melonDS "$BACKUP_DIR/melonDS"

# 6. Gopher64 (N64)
echo "[>] Gopher64..."
mkdir -p "$BACKUP_DIR/Gopher64"
cp -r ~/.var/app/io.github.gopher64.gopher64/config/mupen64plus/save "$BACKUP_DIR/Gopher64/"

# 7. mGBA (GBA)
echo "[>] mGBA..."
[ -d ~/.var/app/io.mgba.mGBA/data/mGBA/saves ] && cp -r ~/.var/app/io.mgba.mGBA/data/mGBA/saves "$BACKUP_DIR/mGBA"

# 8. PPSSPP (PSP)
echo "[>] PPSSPP..."
mkdir -p "$BACKUP_DIR/PPSSPP"
cp -r ~/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SAVEDATA "$BACKUP_DIR/PPSSPP/"

# 9. Cemu (Wii U)
echo "[>] Cemu..."
mkdir -p "$BACKUP_DIR/Cemu"
cp -r ~/.var/app/info.cemu.Cemu/data/cemu/mlc01/usr/save "$BACKUP_DIR/Cemu/"

# 10. Ryujinx (Switch)
echo "[>] Ryujinx..."
mkdir -p "$BACKUP_DIR/Ryujinx"
cp -r ~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/bis/user/save "$BACKUP_DIR/Ryujinx/"

# 11. DuckStation (PS1 - AppImage)
echo "[>] DuckStation..."
cp -r ~/.local/share/duckstation/memcards "$BACKUP_DIR/DuckStation"

echo "------------------------------------------"
echo "[*] Création de l'archive finale..."
tar -czf "$HOME/Desktop/Saves_Emulateurs.tar.gz" -C "$HOME/Desktop" "Backup_Saves_$(date +%Y-%m-%d)"

echo "--- ✅ Terminé ! Archive créée sur le Bureau : Saves_Emulateurs.tar.gz ---"