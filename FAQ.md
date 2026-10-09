# Dolphin for PS4: FAQ

Answers to the questions and problems players have run into. If yours isn't here, ask on the
[Discord](https://discord.gg/QwtU8ZaCth) or [open an issue](https://github.com/iHaiDeeZ/DolphinPS4/issues).

- [Installing and updating](#installing-and-updating)
- [Wii Menu and online play](#wii-menu-and-online-play)
- [Games and saves](#games-and-saves)
- [Controls](#controls)
- [Speed and stutter](#speed-and-stutter)
- [Crashes, freezes and bug reports](#crashes-freezes-and-bug-reports)

## Installing and updating

**The in-app update says "update failed".**
Dolphin downloads updates from GitHub. If it fails, check the console is online and that your
DNS isn't blocking it (see the next question). You can always download the latest `.pkg` from the
[releases page](https://github.com/iHaiDeeZ/DolphinPS4/releases/latest) and install it over the
old one; your settings and saves stay.

**I use a DNS that blocks PS4 firmware updates. Does that matter?**
Yes. Many of those DNS servers block much more than Sony's update servers, including
**Nintendo's servers that the Wii Menu download uses**, and sometimes other downloads (updates,
covers). If a download fails, switch the PS4's DNS back to *Automatic* (or to a DNS that only
blocks Sony's update servers), do the download, then switch back. Keep the PS4's own system
software updates turned off while you do.

**There's no `DolphinPS4` folder in `/data`.**
Dolphin creates `/data/DolphinPS4/` the first time it starts. Start the app once, then put your
games in `/data/DolphinPS4/games/`.

**The app crashes as soon as I start it.**
Turn off your GoldHEN plugins and try again. A plugin that loads into every app (for example
OrbisNet) crashed Dolphin before it even started. If it works without plugins, turn them back on
one at a time to find the one that clashes.

## Wii Menu and online play

**How do I get the Wii Menu?**
*Settings → Wii Menu*: choose your region, then install. Dolphin downloads it from Nintendo's
servers. If the download fails, see the DNS question above.

**Which region should I pick?**
The same region as your games. A Japanese Wii Menu won't start US or European discs from inside
the menu, and its menus are in Japanese. Games you start from Dolphin's own game list work with
any region.

**My Wii Menu seems broken.**
Download it again from *Settings → Wii Menu*, with the right region. If the download fails, check
your DNS first.

**Can I play Wii games online?**
Not yet. Wiimmfi (the replacement for Nintendo's servers) refuses Dolphin's built-in Wii system
with "access denied". It needs the data from a real Wii console, which the app can't import yet.

## Games and saves

**"Something is wrong with this game file".**
The game file is damaged or incomplete, usually from an interrupted copy or a bad dump. Copy it
again (and compare its size with the original), or dump the disc again.

**Where are my saves?**
- GameCube: `/data/DolphinPS4/User/GC/<USA, EUR or JAP>/Card A/`, one `.gci` file per save.
- Wii: `/data/DolphinPS4/User/Wii/title/00010000/<game ID in hex>/data/`. For example, Mario
  Kart Wii (USA, ID `RMCE`) saves to `.../00010000/524d4345/data/`.

You can copy saves from Dolphin on a PC into the same places.

**Which file format should I use?**
RVZ: it's much smaller than ISO and loads just as fast. Dolphin on a PC can convert your games
(right-click → *Convert File*).

**RetroAchievements says "Unknown game".**
RetroAchievements only knows certain dumps of each game. A different region or a modified dump
isn't recognised. Log in under *Settings → RetroAchievements*.

**I can't load a save state.**
Save states are off in RetroAchievements *Hardcore* mode. Hardcore is off by default.

## Controls

**How do I open the in-game menu?**
Press **L3 + R3**. Quick save is **L1 + R3**, quick load is **R1 + L3**.

**How do I plug in or remove the Nunchuk?**
In the game's settings, or with L3 + R3 → *Wii Extension*. It applies to every controller. If you
change it during a game, controllers 2–4 only pick it up after you restart the game.

**Tilting the controller does nothing in Wii games.**
Motion controls need an official DualShock 4; many third-party controllers have no motion
sensors. Also check *Settings → System → Motion Controls* is On. You can steer or tilt with the
left stick instead: *Tilt With → Left Stick*.

**Can I use the touchpad?**
Yes, in Wii games: *Settings → System → Touchpad*. *Pointer* aims with your finger, *Swing*
swings the Wii Remote with a quick swipe. Clicking the touchpad is still HOME.

**How do I use a PS Move as the Wii Remote?**
Pair the Move with the PS4, set *Settings → System → Wii Remote Controller* to *Auto*, and turn
the Move on **before** you start the game. Press Start + Select together to re-centre the pointer.
The DualShock 4 then acts as the Nunchuk.

## Speed and stutter

**Why does a game slow down in busy scenes?**
The PS4's CPU is usually the limit, not its GPU. Leave *Emulated CPU Clock* on *Auto*, and keep
*Game Settings Center* on: it applies tested settings for many games automatically.

**I have a PS4 Pro. Can it go faster?**
Yes: turn on *PS4 Settings → System → Boost Mode*, then close and restart Dolphin. Its CPU then
runs about 30% faster. Don't edit `param.sfo` to force "Neo mode"; it isn't faster and made Mario
Kart freeze.

**The game hitches the first time an effect appears.**
Its shader is being compiled and saved, so it won't happen there again. *Shader Compilation →
Hybrid Ubershaders* avoids even the first hitch, at some GPU cost.

**The game stutters when it loads new areas.**
Usually the PS4's hard drive is reading new game data; it's worst in the first minutes of a
session.

## Crashes, freezes and bug reports

**A game freezes or the picture locks up, often while loading.**
Open the game's settings and set *Speed Features* to *Compatible*. If it still happens, also try
*Synchronize GPU Thread → On* (in newer versions). Please report the game either way.

**A game crashed and Dolphin went back to the game list.**
Dolphin saves a `crash.log`. Please send it with the files listed below.

**Dolphin crashed when I started a Wii game (firmware 12.02, error CE-34878-0).**
That came from the PS Move support and is fixed in v04.01. Update the app.

**How do I report a bug?**
Turn on *Settings → Diagnostics → All Diagnostics*, play until the problem shows up, then
[open an issue](https://github.com/iHaiDeeZ/DolphinPS4/issues) or post on the Discord. Attach
`boot-trace.log` and `dolphin.log` from `/data/DolphinPS4/`, plus `crash.log` or any
`*-stacks*.txt` file if there is one, and say which game, its region and the app version
(*Settings → About*).
