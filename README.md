# Ren'Py Live Variable Editor

A lightweight, drop-in variable browser and editor for Ren'Py games.

Search variables, inspect their current values, edit them in-game, pin the ones you care about, and lock values in place.

## Features

* Browse Store and Persistent variables, with search by name, value, or type
* Numbers-only view by default, which keeps large games fast (switch to all types when needed)
* Edit values in-game
* Pins: keep a list of variables with notes, saved per game
* Locks: keep a pinned value exactly at X, at least X, or at most X
* Change tracking: highlight what changed since the browser was last closed or since a snapshot, and narrow down which variable is which
* Optional Deep mode for nested values
* Configurable hotkey
* Single `.rpy` file, no external tools required

## Installation

1. Download `renpy_live_variable_editor.rpy`
2. Copy it into the game's `game/` folder.

Example:

```text
GameName/
├── GameName.exe
└── game/
    ├── renpy_live_variable_editor.rpy
    ├── script.rpy
    └── ...
```

3. Start the game and load a save or create a new game.
4. Press **F8** to open the editor.

Press **F8** again or **Escape** to close it.

> Make sure you do not have an older copy of the variable browser installed at the same time.

## Usage

The window has two tabs: **Browse** and **Pins**.

In Browse, search for a variable, click it, change the value, then press **Apply**.

Accepted values:

```text
999
12.5
True
False
None
"hello"
[1, 2, 3]
{"key": 5}
```

For string variables, plain text usually works without quotes.

Notes on editing:

* Integer variables reject non-whole numbers instead of silently rounding them.
* Tuple items are read-only.
* Values too large to edit as text (over 20,000 characters) are read-only.

## Numbers Only and Deep Mode

By default the Browse tab lists only `int` and `float` variables. Everything else is skipped while scanning, which is what makes it fast in games with a lot of variables. Boolean flags are not counted as numbers.

Press **Types: Numbers** to switch to **Types: All** to see strings, lists, objects and booleans. This is slower in large games.

Fast mode shows top-level variables. Enable **Deep** to include values nested inside lists, dictionaries, tuples, and objects. Deep mode is bounded per variable so one large structure cannot stall the scan, and it is slower in larger games.

To start in All mode, change this line:

```python
_VB_NUMBERS_ONLY_DEFAULT = False
```

## Pins

Select a variable in Browse and press **Pin**. Pinned variables appear in the **Pins** tab, where you can:

* see their live values
* edit them without searching again
* add a note (for example "Aiko affection")
* set a lock
* unpin them

Pins are saved per game in `variable_browser_pins.json` in the game's save folder. They are stored by variable path, so they keep working as values change. A pin whose variable does not exist yet stays in the list and can still be unpinned or edited.

## Locks

A pinned variable can be locked, similar to freezing a value in Cheat Engine:

* **Exactly**: the variable is set back to the chosen value whenever it changes
* **At least**: the variable is never allowed to go below the chosen value
* **At most**: the variable is never allowed to go above the chosen value

Leave the value box blank to use the variable's current value. At least and At most only work on numbers.

Locks are only enforced while the **Locks** switch in the header is On. The switch starts Off each time the game launches, so a saved lock never changes a game you just opened. To have saved locks start enforcing immediately, change:

```python
_VB_LOCKS_START_ENABLED = True
```

Locks are re-applied about 20 times per second while the game is waiting for input or showing dialogue, and at the start of every interaction. If a game changes a variable and reads it back within a single stretch of script with no interaction in between, it can still see the unlocked value.

If you press **Apply** on a variable with an Exactly lock, the lock moves to the new value.

## Change Tracking

The Browse tab can compare the current values against a baseline. **Compare to** selects one:

* **Last close**: values as they were when you last closed the browser. This is recorded automatically, so after making a choice in the game and reopening the browser, changed variables are highlighted.
* **Snapshot**: values as they were when you pressed **Take snapshot**.
* **Off**: no comparison.

Changed rows are coloured: green for a number that went up, red for one that went down, orange for other changes, blue for new variables. Each shows its previous value, for example `was 200 (+50)`. Pinned variables show the same note in the Pins tab.

The **Show** buttons filter the list to Any, Changed, Unchanged, Up, or Down.

### Finding a variable

To find which variable controls something, such as an affection meter:

1. Press **Take snapshot**.
2. Do something in the game, then reopen the browser.
3. Set **Show** to Changed.
4. Press **Narrow to shown**. This keeps only the matching rows and takes a new snapshot.
5. Repeat with other actions until only a few candidates remain, then pin the right one.

**Reset narrowing** clears the candidate list.

A snapshot covers Store and Persistent variables. Nested values are included only when Deep is on. To turn off the automatic recording when the browser closes, change:

```python
_VB_AUTO_BASELINE = False
```

## Persistent Variables

Be careful when editing or locking variables beginning with:

```text
persistent.
```

Edits are written to Ren'Py's persistent data and may remain after restarting the game or loading another save. A lock on a persistent variable keeps rewriting it while enabled.

## Changing the Hotkey

F8 is used by default.

Change this line in the script:

```python
_VB_HOTKEY = "K_F8"
```

For example:

```python
_VB_HOTKEY = "K_F9"
```

The hotkey is registered through `config.keymap` and `config.underlay`. If it does not respond in a particular game, that game may be rebinding the key or blocking input, so try a different key.

## Compatibility

The script is written to run on both Ren'Py 7.x (Python 2.7) and Ren'Py 8.x (Python 3), using runtime feature checks instead of version checks.

The earlier version was tested with Ren'Py 8.1.3+. The current version, including pins, locks, and change tracking, has not yet been tested across Ren'Py versions. If something fails to load in a particular game, please open an issue with the Ren'Py version and the error from `traceback.txt` or `log.txt`.

## Disclaimer

This is a debugging/modding utility.

Changing unexpected variables can break game logic, saves, or persistent data, so use it carefully.
