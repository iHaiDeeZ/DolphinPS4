<p align="center">
  <img src="docs/images/banner.png" alt="Dolphin for PS4" width="100%">
</p>

<p align="center">
  <a href="https://github.com/iHaiDeeZ/DolphinPS4/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/iHaiDeeZ/DolphinPS4?label=release&color=5bb8ff"></a>
  <img alt="PS4 homebrew" src="https://img.shields.io/badge/PS4-homebrew-1f5fd6">
  <img alt="GameCube and Wii" src="https://img.shields.io/badge/GameCube%20%2B%20Wii-Dolphin-5cd3ff">
  <a href="https://discord.gg/QwtU8ZaCth"><img alt="Discord" src="https://img.shields.io/badge/Discord-join%20the%20testers-5865F2?logo=discord&logoColor=white"></a>
  <a href="LICENSE"><img alt="GPL-2.0-or-later" src="https://img.shields.io/badge/license-GPL--2.0--or--later-ff9ccf"></a>
</p>

<h3 align="center">Your GameCube and Wii library, on the PS4.</h3>

<p align="center">
  <a href="https://github.com/iHaiDeeZ/DolphinPS4/releases/latest"><b>⬇ Get the latest version</b></a> ·
  <a href="https://discord.gg/QwtU8ZaCth">Discord</a> ·
  <a href="#getting-started">Getting started</a> ·
  <a href="#controls">Controls</a> ·
  <a href="#faq">FAQ</a> ·
  <a href="CREDITS.md">Credits</a>
</p>

---

## Overview

Dolphin for PS4 brings the [Dolphin](https://dolphin-emu.org) emulator to jailbroken PS4 consoles
as an app you launch from the home screen like any other. You browse your box art in a
cover-flow library (or a PSP-style XMB, if you prefer), press **Cross**, and play with a DualShock 4. Pressing **L3 + R3**
during a game pauses it and opens a menu for save states, settings and cheats.

Under the hood, Dolphin's JIT recompiler runs on the PS4's CPU, and rendering goes through
Vulkan: Mesa's RADV driver, adapted to submit work directly to the PS4's AMD GPU.

You bring your own game backups. Nothing copyrighted is bundled: no games, BIOS or keys.

## Highlights

**A launcher made for the couch**
- Your games as a row of covers, with the selected one up front, its title, platform and when you
  last played it. Tabs for Library, Memory Cards, Settings and Themes switch with **L1 / R1**.
- **OPTIONS** sorts the games A-Z, by Recently Played or by Platform; **Square** looks for new games.
- Prefer the PSP look? **Settings → Menu Style → XMB** brings back the columns, with purple badges
  for GameCube games and white ones for Wii games.
- Box art is fetched from GameTDB on its own each time the app starts, only for the games that
  are still missing a cover. GameCube discs without art show their built-in banner.
- It remembers the last game you played and starts there. A short animated intro plays at
  launch and when you come back from a game.

**Every game tuned the way you like**
- Each setting can be global or saved for a single game. Switch a game to *This Game* and it
  keeps its own copy; switch it back and it follows the global values again.
- Settings changed in the middle of a game stick.
- The app ships with settings tested on a base PS4, plus ready-made fixes for some games, such as
  Wii Sports without a Nunchuk and sideways Wii Remote games.
- Cheat codes (Action Replay and Gecko) can be switched on per game, from the launcher or the
  pause menu. Each code shows a green ON or red OFF tag, and *Enable All* / *Disable All* flip
  them in one go.

**Memory cards you can see**
- Every GameCube save shows up with its own icon, title, size and date, in both menu styles.
- Make a new, empty memory card for a fresh playthrough or a second player, and choose which card
  sits in Slot A. Your other cards keep their saves.

**Play together**
- Up to four players, each on their own DualShock 4. Turn on another controller, pick a PS4 user
  for it, and it becomes the next player, even in the middle of a game.
- Games only see the controllers that are really there, so nobody gets an empty extra port.

**A pause menu on L3 + R3**
- Eight save state slots, each marked Empty or Other Version when it can't be loaded.
- All settings, applied immediately.
- For Wii games, plug the Nunchuk in or out, or turn the Wii Remote sideways, without leaving
  the game.
- Quit straight back to the launcher.

**Make it yours**
- Twelve colour themes, from *Dolphin Blue* and *GameCube Indigo* to *Wii White* and
  *Midnight*.
- Drop PNG images in a folder to use them as wallpapers, or WAV files to replace the menu sounds.
- Remap the GameCube controller and the Wii Remote, with the DualShock 4 buttons shown as
  icons. The layout you pick is used by every player.

**Built for the PS4's hardware**
- Shaders are compiled in the background on spare CPU cores, and the cache is kept for next
  time.
- An automatic CPU clock that slows the emulated GameCube CPU down in heavy scenes, so games keep
  their normal speed instead of dragging, and brings it back up when a game starts dropping
  frames of its own.
- Pressure-sensitive L and R: a partial pull reaches the game as a partial press, and the
  click comes at the end of the pull.
- An *Auto (60/30)* frame limit that switches to a steady 30 FPS when a game can't hold 60.
- Logs, freeze reports and a profiler you can switch on when something needs investigating.

## Getting started

**You need:** a jailbroken PS4 that runs homebrew packages (developed on a launch-model "fat"
PS4), an FTP connection to it, and backups of games you own.

1. Grab **`DolphinPS4-v03.33.pkg`** from the [releases page](https://github.com/iHaiDeeZ/DolphinPS4/releases/latest)
   and install it with your package installer.
2. Put your games in **`/data/DolphinPS4/games/`**. Accepted formats are `.rvz`, `.iso`,
   `.nkit.iso`, `.gcm`, `.gcz`, `.ciso`, `.wia`, `.wbfs` and `.tgc` (discs), `.wad` (WiiWare,
   Virtual Console, channels), and `.dol` / `.elf` (homebrew). Multi-disc games just need
   `(Disc 1)` / `(Disc 2)` in their names.
3. Launch **Dolphin** from the home screen.

> **Tip:** RVZ is the best format to store games in. It's much smaller than ISO and loads just
> as fast. Dolphin on a PC can convert your games (right-click → *Convert File*).

**Updating:** install the newer package on top of the old one. Everything you've set up lives in
`/data/DolphinPS4/` and survives updates. **Settings → About** shows which version you're on.
Dolphin also checks GitHub for new versions: say *Yes* and it downloads the package, checks it and
puts it in `/data/pkg`; then close Dolphin and install it from **Debug Settings → Game → Package
Installer** (or GoldHEN's).

## Controls

### In the launcher

| Press | To |
|---|---|
| D-pad / left stick | Move around |
| L1 / R1 | Scroll five entries at a time |
| Cross | Play the game / confirm |
| Circle | Go back |
| Triangle | Open a game's options (start, game settings, cheats, information) |

### While playing

| Press | To |
|---|---|
| L3 + R3 | Pause and open the menu |
| Left / Right in the menu | Change a value, or choose a save slot |
| Circle in the menu | Go back, or resume the game |

### Default button layout

| | GameCube | Wii Remote + Nunchuk |
|---|---|---|
| Cross | A | A |
| Square | B | 1 |
| Circle | X | – |
| Triangle | Y | 2 |
| R1 | Z | – |
| L1 | – | − and Nunchuk C |
| L2 | L (analog) | Nunchuk Z |
| R2 | R (analog) | B |
| Options | Start | + |
| Touch pad click | – | Home |
| Left stick | Control stick | Nunchuk stick |
| Right stick | C-stick | Pointer |
| R3 | – | Shake |
| D-pad | D-pad | D-pad |

Any of these can be changed under **Settings → Controls**: highlight an input, press Cross, then
press the button you'd like to use.

**More players:** switch on another DualShock 4 and choose a PS4 user for it. Players 2 to 4 use
the same layout on their own controller. The pause menu belongs to player 1.

## Settings at a glance

| Group | Highlights |
|---|---|
| Video | Internal resolution up to 3x, aspect ratio, widescreen hack, letterbox zoom, frame-rate limit, V-Sync, FPS counter |
| Graphics | Texture filtering, anisotropic filtering, anti-aliasing, fog, EFB options, shader compilation mode |
| Performance | Emulated CPU clock (Auto or fixed), Fast / Compatible speed features, dual core, Vulkan thread, fast disc |
| System | Game volume, Wii Nunchuk, sideways Wii Remote, controller in Wii games (Wii Remote, GameCube controller or both), motion controls, PS Move, Wii SD card, audio buffer |
| Diagnostics | One switch for everything, or performance log, freeze reports, emulator log and profiler separately |

The launcher also has switches for its sounds and clock, a cover downloader, the controls editor,
**Reset All Settings** and **About**.

### Game settings center

The best settings found for each game live in
[`xmb/game-settings.ini`](xmb/game-settings.ini). Dolphin downloads it from GitHub every time it
starts online, so a game's fix or speed-up reaches everyone without a new release. Your own
settings (the menu, `ps4.ini`) always win over it.

Before a covered game's first start, Dolphin asks whether to use its recommended settings
(Yes / No). *Settings → Game Settings Center* shows the source, the last update, **Update Now**,
and your games with recommended settings, each switchable between *Used* and *Not used* (also at
the top of the game's own Game Settings).

### Cheats

Triangle on a game → **Cheats** (or L3 + R3 → Cheats while playing).

- **Download Codes** fetches the game's Gecko codes from the internet. New codes arrive switched off.
- **Your own codes:** add them to `/data/DolphinPS4/User/GameSettings/<GAME ID>.ini` (for example
  `GMSE01.ini`, not a `.txt`), under a `[Gecko]` or `[ActionReplay]` line, each code starting
  with a `$Name` line. They then appear in the list to switch on.

## Your files

Everything the app creates sits in **`/data/DolphinPS4/`**:

- `games/`: your game backups
- `covers/`: box art, one `<disc ID>.png` per game. Swap in your own art if you like.
- `themes/`: custom wallpapers (PNG) and menu sounds (`themes/sounds/*.wav`)
- `User/`: Dolphin's own data: GameCube memory cards, the Wii's saves, save states, shader cache
  and controller layouts
- `settings.ini`: your settings, global and per game
- `xmb.ini`: launcher preferences (theme, wallpaper, sounds, last game)
- `ps4.ini`: optional advanced switches, layered on top of the built-in defaults
- `game-settings.ini`: the game settings center's latest copy (downloaded; don't edit)
- `*.log` and `*-stacks*.txt`: logs and freeze reports for bug reports

## Game compatibility

Measured on a launch-model PS4, average frames per second while playing:

| Game | System | FPS |
|---|---|---|
| Super Mario Sunshine | GameCube | 30 (its normal rate) |
| Resident Evil 4 | GameCube | 30 (its normal rate) |
| The Legend of Zelda: Twilight Princess | GameCube | 30 (its normal rate) |
| Mortal Kombat: Deadly Alliance | GameCube | 60 |
| Crash Nitro Kart | GameCube | 60 |
| Crash Tag Team Racing | GameCube | 60 |
| Sonic Adventure DX | GameCube | 60 |
| Shadow the Hedgehog | GameCube | 30–60 |
| Worms 3D | GameCube | ~55 |
| Super Smash Bros. Melee | GameCube | 36–60 |
| Crash Bandicoot: The Wrath of Cortex | GameCube | 20–60 |
| FIFA Street 2 | GameCube | ~34 |
| Spider-Man 2 | GameCube | 15–29 (its normal rate is 30) |
| Call of Duty 2: Big Red One | GameCube | 15–20 (its normal rate is 30) |
| Super Mario Galaxy | Wii | 40–57 |
| Wii Sports | Wii | ~40 |
| Wii Sports Resort | Wii | ~37 |
| Bully: Scholarship Edition | Wii | 15–30 (its normal rate is 30) |

A range means the frame rate depends on what's on screen.

**Reported by testers** on the [Discord](https://discord.gg/QwtU8ZaCth):

| Game | System | Console | Resolution | Result |
|---|---|---|---|---|
| Super Smash Bros. Melee (Akaneia / ACE mod) | GameCube | PS4 Slim, 11.00 | 1080p | 60 FPS, very stable, no stutters or crashes |
| Dragon Ball Z: Budokai | GameCube | PS4 Slim, 12.52 | 1080p | 60 FPS, stable, no stutters or crashes |
| The Legend of Zelda: Four Swords Adventures | GameCube | PS4 Slim, 11.02 | 1080p | Steady 60 FPS most of the time |
| The Legend of Zelda: Twilight Princess | GameCube | PS4 Slim, 12.52 | 1080p | 28 FPS, stable, no stutters or freezes |
| Spider-Man 2 | GameCube | PS4 Slim, 12.52 | 1080p | ~25 FPS, dips to 80% speed, some stutters, no crashes |
| Dead to Rights | GameCube | PS4 Slim, 12.52 | 720p | 45–50 FPS, speed dips, some stutters, no crashes |
| Mario Kart: Double Dash!! | GameCube | PS4 Pro, 9.60 | 1080p | 60 FPS, very smooth, no stutters or crashes |
| Pokémon Colosseum | GameCube | PS4, 13.52 | – | 30 FPS in gameplay and cutscenes (60 in menus), 100% speed |
| Pokémon XD: Gale of Darkness | GameCube | PS4, 13.52 | – | 25–30 FPS, heavier scenes ~20, playable |
| Super Paper Mario | Wii | – | 1080p | 50–60 FPS, stable, playable |
| "Pokémon Stadium" (name as reported) | – | – | 1080p | 30 FPS, a small drop at the start of battles, saves work |
| Super Smash Bros. Brawl | Wii | PS4 Slim, 11.00 | 1080p | 60 FPS, stutters on some stages, no crashes |
| Mario Kart Wii | Wii | PS4 Slim, 11.00 | 1080p | 40–50 FPS, sometimes full speed, some stutters, no crashes |
| PokéPark 2: Wonders Beyond | Wii | PS4, 13.52 | – | 30 FPS, 100% speed; turn on *Sideways Wii Remote* for the D-pad |
| Crash of the Titans | Wii | PS4 Pro, 13.52 | 1080p | Doesn't start: loops at the beginning |

Tested a game that isn't listed? Tell us on the [Discord](https://discord.gg/QwtU8ZaCth) or in an
[issue](https://github.com/iHaiDeeZ/DolphinPS4/issues): the game, your console and firmware, the
resolution and how it ran.

## FAQ

**Why does a game slow down in busy scenes?**
The PS4's CPU is usually the bottleneck, not its GPU. Leave the emulated CPU clock on *Auto*. If
the frame rate wanders between 45 and 55 and feels choppy, *Frame Rate Limit → Auto (60/30)*
gives a smoother, steady 30.

**The game hitches the first time an effect appears. Why?**
Its shader is being compiled. It's saved to the cache, so it won't happen there again. The
*Hybrid Ubershaders* mode avoids even the first hitch, at some GPU cost.

**A game shows glitches or locks up.**
Open its Game Settings and set *Speed Features* to *Compatible*. If it still happens, please
report it.

**Tilting the controller does nothing in Wii games.**
Motion controls need an official DualShock 4. Many third-party controllers have no motion
sensors: the PS4 then reports a controller that never moves. Also check *Settings → System →
Motion Controls* is On.

**A Wii game tells me to disconnect the Nunchuk.**
Press L3 + R3 and set *Wii Extension* to *None*. The game remembers it.

**Some covers are missing.**
The console has to be online when the app starts. GameTDB doesn't have art for every disc, so
you can put your own PNG in `covers/`.

**How do I report a bug?**
Turn on *Settings → Diagnostics → All Diagnostics*, play until the problem shows up, then
[open an issue](https://github.com/iHaiDeeZ/DolphinPS4/issues). Attach `boot-trace.log` and
`dolphin.log` from `/data/DolphinPS4/`, plus `crash.log` or any `*-stacks*.txt` file if there is
one, and mention the game, its region and the app version.

## Testing and feedback

Want to help test new versions, report a game that misbehaves or share frame rates? Join the
**[Dolphin for PS4 Discord](https://discord.gg/QwtU8ZaCth)**. When you report a problem, say which
game and version (**Settings → About**) you used, and attach `/data/DolphinPS4/dolphin.log` if you can.

## Good to know

- Games built around Wii Remote pointing or motion are hard to play on a DualShock 4.
- Save states carry over to new versions unless a release says otherwise. A state an update can't load is
  marked "Other Version" in the menu and is never loaded halfway, but in-game saves are the safe place for progress.
  In-game saves are never affected.
- Netplay, achievements and texture packs aren't supported on the PS4.
- Only the original PS4 has been tested so far. PS4 Pro reports are welcome.

## Thanks

- **[Dolphin](https://dolphin-emu.org)**: the emulator itself, from its creators **F|RES** and
  **ector** to the hundreds of people who have contributed since
- **[Mesa](https://mesa3d.org)**: the RADV Vulkan driver that draws every frame
- **[OpenOrbis](https://github.com/OpenOrbis)** and **[PacBrew](https://github.com/PacBrew)**: the
  PS4 toolchains
- **[love-ps4](https://github.com/Mari0/love-ps4)**: the reference PS4 setup
- **[GameTDB](https://www.gametdb.com)**: game titles and box art

Everyone involved, with licences, is listed in **[CREDITS.md](CREDITS.md)**.

## License and disclaimer

Released under **GPL-2.0-or-later**, the same licence as Dolphin. See [LICENSE](LICENSE).

This is a fan-made project with no ties to Nintendo, Sony Interactive Entertainment or the
Dolphin Emulator Project. GameCube and Wii are trademarks of Nintendo; PlayStation and PS4 are
trademarks of Sony Interactive Entertainment. Please only play games you own. This project won't
help you find or share game files.
