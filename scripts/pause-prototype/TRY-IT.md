# Try it: pause by sentence for Spoken (prototype)

An **unofficial test build** of [Spoken](https://github.com/rusty-key/spoken-wow). It has been proposed to Spoken's developers but isn't part of Spoken. It adds a real **Pause**:

| Button | Then **Play** | **Replay** |
| --- | --- | --- |
| **Pause** (two bars) | starts the **current sentence** again | the whole line |
| **Stop** (square) | goes back to the **start of the text on screen** | the whole line |

WoW can't pause a sound, so this tool cuts each line of Spoken's voice packs into sentences **on your own computer**. That takes 10–30 minutes, once. You need about **3 GB of free space** while it works. Everything is backed up, and one command puts it all back.

## 1. Before you start

1. Install **Spoken and its voice packs** as usual, with Spoken Manager or CurseForge, and check that they work in game.
2. **Turn off automatic updates** for Spoken in Spoken Manager or CurseForge while you test. An update would overwrite the test build.
3. **Close WoW.**

## 2. Install Python and ffmpeg (once)

**Windows:** open **Terminal** (or PowerShell) and run:
```
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```
Then **close Terminal and open a new one**, so it finds them.

**Mac:** open **Terminal** (Applications → Utilities) and run:
```
xcode-select --install
```
That installs Python 3; click Install if a window asks. Then install Homebrew from https://brew.sh if you don't have it, and run:
```
brew install ffmpeg
```

## 3. Install the test build

Unzip this download anywhere, such as your Downloads folder.

**Windows:** double-click **`try-it-windows.bat`** and type `install`.

**Mac:** in Terminal, go to the unzipped folder and run the tool. Typing `cd ` and then dragging the folder onto the Terminal window fills in the path:
```
cd ~/Downloads/spoken-pause-prototype
python3 spoken_pause.py install
```
You can also double-click `try-it-mac.command`. If the Mac says it can't be opened, right-click it, choose **Open**, then **Open** again.

It finds WoW by itself in the usual places. If it can't, it tells you how to point it at your `_forever_\Interface\AddOns` folder.

## 4. Play

Start WoW, accept a quest, and try **Pause**, **Stop**, **Play** and **Replay**. Pause and Stop work in every Spoken window style and in the minimap menu. There are also key bindings under **Key Bindings → Spoken**.

Please tell whoever sent you this:
- whether you can hear the joins between sentences;
- whether logging in feels slower;
- anything that looks or sounds wrong.

## 5. Put everything back

Close WoW. Then on **Windows** double-click `try-it-windows.bat` and type `restore`, or on a **Mac** run:
```
python3 spoken_pause.py restore
```
Your original Spoken and voice packs come back exactly as they were. Then you can turn automatic updates back on.

`python3 spoken_pause.py status` (or the `.bat`, then Enter) shows what's installed.
