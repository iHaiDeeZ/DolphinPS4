# 🐬 Dolphin for PS4 — Quick Start

## 📁 Where to put your games
Copy your games (FTP) to:
```fix
/data/DolphinPS4/games
```
> 💡 Want a USB drive or another folder? ***Settings → Game Folder*** lets you pick any folder, including `/mnt/usb0`.

## 💾 Memory cards
Open the ***Memory Cards*** tab in the menu to **create cards**, **see your saves** and choose the card in **Slot A**.
```yaml
Memory Card 1: /data/DolphinPS4/User/GC/<USA|EUR|JAP>/Card A
Extra cards:   /data/DolphinPS4/User/GC/Cards
```

## 🩺 Turn off diagnostics (a bit faster)
Diagnostics are **ON by default**, so your logs can help us fix bugs.
```diff
+ Settings → Diagnostics → All Diagnostics → Off
```
> ⚠️ A game with its own ***custom settings*** (**Triangle** on the game) keeps its own switch — turn it off there too.
> 🐞 Crash or freeze? Turn it back **on**, play until it happens, and send us `/data/DolphinPS4/boot-trace.log`.

## 🎮 Supported formats
```diff
+ GameCube & Wii discs:   .iso .gcm .ciso .gcz .wbfs .wia .rvz .nkit.iso
+ GameCube demo discs:    .tgc
+ WiiWare / VC / channels: .wad
+ Homebrew:               .dol .elf
```
-# ⭐ **.rvz** is the smallest. Multi-disc games: name them `Game (Disc 1).rvz`, `Game (Disc 2).rvz`.
