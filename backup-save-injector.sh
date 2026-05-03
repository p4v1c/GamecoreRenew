#!/bin/bash

BACKUP_DATE="2026-05-01" 
SOURCE_DIR="$HOME/Desktop/Backup_Saves_$BACKUP_DATE"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "❌ Erreur : Le dossier source $SOURCE_DIR n'existe pas."
    exit 1
fi

echo "--- 📥 Début de la restauration des sauvegardes ---"

restore_item() {
    local src="$1"
    local dest="$2"
    if [ -d "$src" ] || [ -f "$src" ]; then
        echo "[>] Restauration : $(basename "$src")..."
        mkdir -p "$(dirname "$dest")"
        cp -r "$src" "$dest"
    else
        echo "[!] Ignoré : $src non trouvé dans le backup."
    fi
}

# 1. Azahar (3DS)
restore_item "$SOURCE_DIR/Azahar/nand" ~/.var/app/org.azahar_emu.Azahar/data/azahar-emu/
restore_item "$SOURCE_DIR/Azahar/sdmc" ~/.var/app/org.azahar_emu.Azahar/data/azahar-emu/

# 2. RPCS3 (PS3)
restore_item "$SOURCE_DIR/RPCS3/savedata" ~/.var/app/net.rpcs3.RPCS3/config/rpcs3/dev_hdd0/home/00000001/

# 3. PCSX2 (PS2)
restore_item "$SOURCE_DIR/PCSX2" ~/.var/app/net.pcsx2.PCSX2/config/PCSX2/memcards

# 4. Dolphin (GC/Wii)
restore_item "$SOURCE_DIR/Dolphin/GC" ~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/
restore_item "$SOURCE_DIR/Dolphin/title" ~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Wii/

# 5. melonDS (DS)
restore_item "$SOURCE_DIR/melonDS" emu/melonds/

# 6. Gopher64 (N64)
restore_item "$SOURCE_DIR/Gopher64/save" ~/.var/app/io.github.gopher64.gopher64/config/mupen64plus/

# 7. mGBA (GBA)
restore_item "$SOURCE_DIR/mGBA" ~/.var/app/io.mgba.mGBA/data/mGBA/saves

# 8. PPSSPP (PSP)
restore_item "$SOURCE_DIR/PPSSPP/SAVEDATA" ~/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/

# 9. Cemu (Wii U)
restore_item "$SOURCE_DIR/Cemu/save" ~/.var/app/info.cemu.Cemu/data/cemu/mlc01/usr/

# 10. Ryujinx (Switch)
restore_item "$SOURCE_DIR/Ryujinx/save" ~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/bis/user/

# 11. DuckStation (PS1)
restore_item "$SOURCE_DIR/DuckStation" ~/.local/share/duckstation/memcards

echo "--- ✅ Restauration terminée ! ---"