# Ren'Py Live Variable Browser + Editor (updated)
# File: renpy-live-variable-editor-renpy7-updated.rpy
#
# Drop this file into the game's "game/" folder.
# IMPORTANT: remove/rename any older copy (variable_browser.rpy, the original
# renpy-live-variable-editor-renpy7.rpy, ...) so two versions aren't loaded.
#
# Written for Ren'Py 7.x (Python 2.7); the code is also meant to run on
# Ren'Py 8.x (Python 3). It has not been run inside Ren'Py yet -- keep the
# original file as a backup.
#
# Default hotkey: F8 (change _VB_HOTKEY below if needed).
# Browse tab: click a variable -> edit its value -> Apply. Press Pin to keep it.
# Pins tab:   your pinned variables, with notes and optional locks.
# Fast mode is default; toggle Deep to include nested list/dict/object values.
#
# PINS
#   Pinned variables are listed in the Pins tab so you don't have to search for
#   them again. Each pin can have a note (description). Pins are saved per game
#   in the game's save folder as variable_browser_pins.json.
#
# LOCKS (like freezing a value in Cheat Engine)
#   Each pin can be locked:
#     Exactly X   the variable is forced back to X whenever it changes
#     At least X  the variable is never allowed to go below X
#     At most X   the variable is never allowed to go above X
#   Leave the value box blank to use the variable's current value.
#   Locks are re-applied about 20 times a second while the game is waiting for
#   input/running dialogue (and at the start of every interaction). If a game
#   changes a variable and reads it back within one stretch of script, without
#   any interaction in between, it can still see the unlocked value.
#   Lock settings are saved with the pin, but the master "Locks" switch starts
#   OFF each launch (see _VB_LOCKS_START_ENABLED) so nothing is forced on you.
#
# TYPES (Browse tab)
#   The "Types" button cycles between three views:
#     Numbers          int/float variables only
#     Numbers + flags  int/float plus True/False variables (default)
#     All              everything: strings, lists, objects, ... (slower)
#   Anything outside the chosen view is skipped while scanning (no repr is
#   built for it), which keeps big games fast. Set _VB_TYPES_DEFAULT to
#   "numbers", "flags" or "all" to change the starting view. Pins can be any
#   type regardless of this setting.
#
# CHANGE TRACKING / SCANNING (Browse tab, like Cheat Engine's "next scan")
#   "Compare to" picks a baseline:
#     Last close  values as they were when you last closed the browser
#                 (recorded automatically, so after making a choice in the game
#                 and reopening, changed variables are highlighted)
#     Snapshot    values as they were when you pressed "Take snapshot"
#   Changed rows are coloured (green = went up, red = went down, orange =
#   changed, blue = new) and show what they were before.
#   "Show" filters the list: Any / Changed / Unchanged / Up / Down.
#   To hunt for a variable: Take snapshot -> do something in the game -> reopen
#   -> Show: Changed -> "Narrow to shown" (keeps only those rows and takes a
#   fresh snapshot) -> repeat until only a few candidates are left. Then pin it.
#   A snapshot covers Store + Persistent; nested values only if Deep is on.
#
# WARNING: Editing persistent.* variables writes the new value to persistent data
# on disk, so those changes can affect future game sessions.
#
# Values use Python-style literals:
#   999
#   12.5
#   True
#   False
#   None
#   "text"
#   [1, 2, 3]
#   {"key": 5}
#
# Fixes compared with the original:
#   - The edit box holds the FULL repr of the value, not the truncated display
#     text (which used to overwrite long values with "..." on Apply).
#     Values too large to edit as text are read-only.
#   - String editing works on Ren'Py 7 (Python 2 unicode reprs like u'abc').
#   - The row cache is cleared every time the browser opens (no stale values).
#   - Browser state lives in non-rollback objects instead of the store, so it
#     is not written to save files or rewound by rollback.
#   - Tuple items are read-only instead of failing with a TypeError.
#   - Deep mode gives every variable its own row budget, so later variables
#     (and persistent.*) are no longer cut off. "Show more" lists extra rows.
#   - The UI scales to the game's resolution and uses its own fonts/colours.
#   - Hotkey uses config.underlay + a keymap entry instead of an overlay screen.
#   - Values are assigned with setattr/setitem instead of exec.
#   - Whole-number check for int targets, persistent save errors are reported.

init -999 python:
    import ast
    import collections
    import types
    import copy as _vb_copy
    import json as _vb_json
    import os as _vb_os
    import sys as _vb_sys
    try:
        import reprlib
    except ImportError:
        # Ren'Py 7.x uses Python 2.7, where reprlib is named repr.
        import repr as reprlib

    _vb_py2 = (_vb_sys.version_info[0] == 2)

    try:
        _vb_string_types = (basestring,)
        _vb_text_type = unicode
        _vb_int_types = (int, long)
    except NameError:
        _vb_string_types = (str,)
        _vb_text_type = str
        _vb_int_types = (int,)

    _vb_number_types = _vb_int_types + (float,)

    # Change this if F8 conflicts with a game's own key bindings.
    # Examples: "K_F7", "K_F9", "K_F10".
    _VB_HOTKEY = "K_F8"

    # Set to True to have saved locks start enforcing as soon as the game
    # starts. Default is False: the "Locks" switch in the header starts Off.
    _VB_LOCKS_START_ENABLED = False

    # Record a baseline every time the browser closes, so the next open can
    # highlight what changed in between. Set to False to turn that off.
    _VB_AUTO_BASELINE = True

    _VB_PINS_FILENAME = "variable_browser_pins.json"

    _VB_DIFF_COLORS = {
        "up": "#7cfc9a",
        "down": "#ff8a8a",
        "changed": "#ffd080",
        "new": "#9cccff",
    }

    _VB_MAX_ROWS = 300            # rows shown per page ("Show more" adds another page)
    _VB_MAX_SCAN_ROWS = 4000      # deep-mode cap on rows scanned in total
    _VB_MAX_ROWS_PER_ROOT = 100   # deep-mode cap on rows per top-level variable
    _VB_MAX_VISIT_PER_ROOT = 2000 # deep-mode cap on nodes searched per top-level variable
    _VB_MAX_DEPTH = 2

    # Which variables the Browse tab scans by default:
    #   "numbers"  int/float only
    #   "flags"    int/float plus True/False (default)
    #   "all"      everything
    # Anything outside the view is skipped while scanning, which is far
    # faster in big games. Cycle it with the "Types" button in the browser.
    _VB_TYPES_DEFAULT = "flags"
    _VB_MAX_REPR = 500            # display text length in the list
    _VB_MAX_EDIT = 20000          # values with a longer repr are read-only

    # AST node types allowed in a variable path (no calls, lambdas, etc.).
    _VB_SAFE_NODES = frozenset([
        "Expression", "Name", "Attribute", "Subscript", "Load", "Index",
        "Constant", "Num", "Str", "Bytes", "NameConstant", "UnaryOp", "USub",
        "Tuple",
    ])

    _vb_repr = reprlib.Repr()
    _vb_repr.maxlevel = 2
    _vb_repr.maxdict = 12
    _vb_repr.maxlist = 12
    _vb_repr.maxtuple = 12
    # Python 2.7's repr.Repr does not expose every Python 3 reprlib option.
    if hasattr(_vb_repr, "maxset"):
        _vb_repr.maxset = 12
    if hasattr(_vb_repr, "maxfrozenset"):
        _vb_repr.maxfrozenset = 12
    _vb_repr.maxstring = 240
    _vb_repr.maxother = 240

    # Browser state. This must not live in plain store variables: those are
    # saved with the game and rewound by rollback. NoRollback objects (and
    # never re-binding the names below) keep the state out of both.
    _VBStateBase = getattr(getattr(renpy, "python", None), "NoRollback", object)

    class _VBState(_VBStateBase):
        def __init__(self):
            # OrderedDict() instead of {} so Ren'Py doesn't wrap it in a
            # rollback-tracking RevertableDict.
            self.cache = collections.OrderedDict()
            self.filtered = collections.OrderedDict()
            self.pins = collections.OrderedDict()   # path -> _VBPin
            self.pins_loaded = False
            self.locks_enabled = _VB_LOCKS_START_ENABLED
            self.status = ""

            # Change tracking. A snapshot maps path -> fingerprint.
            self.diff_cache = collections.OrderedDict()
            self.compare_mode = "close"     # "close", "snap" or "off"
            self.diff_filter = "any"        # any, changed, same, up, down
            self.snap = None
            self.snap_deep = False
            self.snap_version = 0
            self.close_snap = None
            self.close_version = 0
            self.candidates = None          # frozenset of paths, or None
            self.cand_version = 0

            # Type view ("numbers", "flags" or "all"), and the view each
            # baseline was recorded under.
            self.type_mode = _VB_TYPES_DEFAULT
            self.snap_mode = "all"
            self.close_mode = "all"

    class _VBPin(_VBStateBase):
        # mode is "off", "exact", "min" (at least) or "max" (at most).
        def __init__(self, path, note="", mode="off", limit_text=""):
            self.path = path
            self.note = note
            self.mode = mode
            self.limit_text = limit_text   # saved form of the lock value
            self.value = None              # parsed lock value (runtime)
            self.code = None               # compiled path (runtime)
            self.state = ""                # "", "ok", "missing", "error: ..."

    _vb_state = _VBState()

    def _vb_safe_repr(value, limit=_VB_MAX_REPR):
        # reprlib avoids constructing enormous repr strings for large
        # dictionaries/lists, which makes the browser much faster.
        try:
            text = _vb_repr.repr(value)
        except Exception as e:
            text = "<repr failed: %s>" % (e,)

        text = text.replace("\n", "\\n")

        if len(text) > limit:
            text = text[:limit - 3] + "..."

        return text

    def _vb_edit_text(value):
        # Full (not reprlib-shortened) text for the edit box.
        # Returns (text, complete).
        try:
            text = repr(value)
        except Exception as e:
            return "<repr failed: %s>" % (e,), False

        # Python 2 unicode strings repr as u'...'; drop the prefix so the
        # text looks like what the user would type.
        if isinstance(value, _vb_text_type) and text[:2] in ("u'", 'u"'):
            text = text[1:]

        if len(text) > _VB_MAX_EDIT:
            return text[:_VB_MAX_EDIT], False

        return text, True

    def _vb_literal(text):
        # literal_eval that returns text (not bytes) for plain strings on
        # Python 2, to match the unicode strings Ren'Py 7 games use.
        value = ast.literal_eval(text.strip())

        if _vb_py2 and isinstance(value, type(b"")):
            value = value.decode("utf-8")

        return value

    def _vb_clear_cache():
        _vb_state.cache.clear()
        _vb_state.filtered.clear()
        _vb_state.diff_cache.clear()

    def _vb_refresh():
        _vb_clear_cache()
        _vb_state.status = "Variable list refreshed."
        renpy.restart_interaction()

    def _vb_is_noise(name, value):
        if not name or name.startswith("_"):
            return True

        if isinstance(value, (types.ModuleType, type)):
            return True

        if callable(value):
            return True

        return False

    def _vb_is_protected(path):
        # Never let the UI overwrite its own helper/internal variables.
        return path.startswith(("_vb_", "_VB_", "renpy."))

    def _vb_path_is_safe(path):
        # Paths are evaluated as Python expressions, so only accept plain
        # name / attribute / subscript chains (matters for pins loaded from
        # the JSON file, which a person could have edited).
        try:
            tree = ast.parse(path.strip(), mode="eval")
        except Exception:
            return False

        for node in ast.walk(tree):
            if type(node).__name__ not in _VB_SAFE_NODES:
                return False

        return True

    def _vb_can_expand(value):
        if isinstance(value, (dict, list, tuple)):
            return True

        try:
            module_name = type(value).__module__ or ""

            if module_name.startswith(("renpy", "pygame", "builtins", "__builtin__")):
                return False

            return hasattr(value, "__dict__")
        except Exception:
            return False

    def _vb_budget_left(rows, start):
        return (len(rows) < _VB_MAX_SCAN_ROWS
                and len(rows) - start < _VB_MAX_ROWS_PER_ROOT)

    def _vb_is_number(value):
        return isinstance(value, _vb_number_types) and not isinstance(value, bool)

    def _vb_type_ok(value, mode):
        # Is this value part of the given type view?
        if mode == "all":
            return True

        if _vb_is_number(value):
            return True

        return mode == "flags" and isinstance(value, bool)

    def _vb_walk(path, value, depth, rows, seen, start, mode, counter):
        # Children of an object already expanded elsewhere are only listed
        # under the first path that reached it. Outside the "all" view only
        # matching values get a row, but containers are still searched.
        # counter[0] counts nodes visited under the current root, so a huge
        # structure without many matches can't stall the scan.
        counter[0] += 1

        if counter[0] > _VB_MAX_VISIT_PER_ROOT:
            return

        if _vb_type_ok(value, mode):
            rows.append((
                path,
                _vb_safe_repr(value),
                type(value).__name__
            ))

        if depth >= _VB_MAX_DEPTH or not _vb_can_expand(value):
            return

        try:
            ident = id(value)

            if ident in seen:
                return

            seen.add(ident)
        except Exception:
            pass

        try:
            if isinstance(value, dict):
                for key, child in list(value.items())[:250]:
                    if not _vb_budget_left(rows, start):
                        break

                    child_path = "%s[%r]" % (path, key)
                    _vb_walk(child_path, child, depth + 1, rows, seen, start, mode, counter)

            elif isinstance(value, (list, tuple)):
                for i, child in enumerate(value[:250]):
                    if not _vb_budget_left(rows, start):
                        break

                    child_path = "%s[%d]" % (path, i)
                    _vb_walk(child_path, child, depth + 1, rows, seen, start, mode, counter)

            else:
                attrs = vars(value)

                for key in sorted(attrs):
                    if key.startswith("_"):
                        continue

                    if not _vb_budget_left(rows, start):
                        break

                    try:
                        child = attrs[key]
                    except Exception:
                        continue

                    if callable(child):
                        continue

                    child_path = "%s.%s" % (path, key)
                    _vb_walk(child_path, child, depth + 1, rows, seen, start, mode, counter)

        except Exception:
            return

    def _vb_build_rows(scope="all", deep=False):
        # Cache the expensive scan. Ren'Py re-evaluates screens frequently,
        # so rebuilding the variable tree on every interaction is very slow.
        mode = _vb_state.type_mode
        cache_key = (scope, bool(deep), mode)
        cached = _vb_state.cache.get(cache_key)
        if cached is not None:
            return cached

        rows = []
        seen = set()

        def add_root(path, value):
            # Every root always gets its own row; deep mode only limits how
            # much is expanded underneath it. Values outside the type view
            # are skipped before any repr is built, which is what makes
            # large games fast.
            if deep and len(rows) < _VB_MAX_SCAN_ROWS:
                _vb_walk(path, value, 0, rows, seen, len(rows), mode, [0])
            elif _vb_type_ok(value, mode):
                rows.append((path, _vb_safe_repr(value), type(value).__name__))

        if scope in ("all", "store"):
            try:
                items = sorted(vars(renpy.store).items())
            except Exception:
                items = []

            for name, value in items:
                if _vb_is_noise(name, value):
                    continue

                add_root(name, value)

        if scope in ("all", "persistent"):
            try:
                pitems = sorted(vars(persistent).items())
            except Exception:
                pitems = []

            for name, value in pitems:
                if not name or name.startswith("_") or callable(value):
                    continue

                add_root("persistent." + name, value)

        _vb_state.cache[cache_key] = rows
        return rows

    def _vb_collect_rows(query="", scope="all", deep=False, limit=_VB_MAX_ROWS):
        # Returns (rows to show, total matching rows). limit=None means all.
        rows = _vb_build_rows(scope, deep)
        q = (query or "").strip().lower()

        # The Show filter only applies while there is a baseline to compare to.
        filt = _vb_state.diff_filter if _vb_has_baseline() else "any"
        cands = _vb_state.candidates

        if q or filt != "any" or cands is not None:
            key = (
                scope, bool(deep), q, filt, cands is not None,
                _vb_state.type_mode,
                _vb_state.compare_mode, _vb_state.snap_version,
                _vb_state.close_version, _vb_state.cand_version,
            )
            filtered = _vb_state.filtered.get(key)

            if filtered is None:
                diff = _vb_get_diff(scope, deep) if filt != "any" else None

                filtered = [
                    row for row in rows
                    if (not q
                        or q in row[0].lower()
                        or q in row[1].lower()
                        or q in row[2].lower())
                    and (cands is None or row[0] in cands)
                    and (diff is None or _vb_matches_filter(diff.get(row[0]), filt))
                ]

                if len(_vb_state.filtered) > 40:
                    _vb_state.filtered.clear()

                _vb_state.filtered[key] = filtered

            rows = filtered

        return rows[:limit], len(rows)

    # ------------------------------------------------------------------
    # Change tracking: snapshots, diffs, narrowing
    # ------------------------------------------------------------------

    def _vb_fingerprint(value):
        # (hash of the full repr, number or None, short repr for display)
        try:
            text = repr(value)
        except Exception:
            text = "<repr failed>"

        if len(text) > 20000:
            text = text[:20000] + ("%d" % len(text))

        number = None

        if isinstance(value, _vb_number_types) and not isinstance(value, bool):
            number = value

        return (hash(text), number, _vb_safe_repr(value, 60))

    def _vb_fmt_num(number, signed=False):
        if isinstance(number, float):
            return ("%+.10g" if signed else "%.10g") % number

        return ("%+d" if signed else "%d") % number

    def _vb_diff_entry(old, new):
        # old/new are fingerprints. Returns (kind, tag text).
        if old[0] == new[0]:
            return ("same", "")

        if old[1] is not None and new[1] is not None:
            delta = new[1] - old[1]

            if delta > 0:
                kind = "up"
            elif delta < 0:
                kind = "down"
            else:
                kind = "changed"

            return (kind, "was %s (%s)" % (_vb_fmt_num(old[1]), _vb_fmt_num(delta, True)))

        return ("changed", "was %s" % (old[2],))

    def _vb_is_root_path(path):
        if "[" in path:
            return False

        return path.count(".") == (1 if path.startswith("persistent.") else 0)

    def _vb_get_baseline():
        # Returns (snapshot or None, name, version, snapshot was deep,
        # type view the snapshot was recorded under).
        mode = _vb_state.compare_mode

        if mode == "snap":
            return (_vb_state.snap, "snap", _vb_state.snap_version,
                    _vb_state.snap_deep, _vb_state.snap_mode)

        if mode == "close":
            return (_vb_state.close_snap, "close", _vb_state.close_version,
                    False, _vb_state.close_mode)

        return None, "off", 0, False, "all"

    def _vb_has_baseline():
        base = _vb_get_baseline()[0]
        return base is not None and len(base) > 0

    def _vb_compute_diff(base, base_deep, base_mode, scope, deep):
        result = collections.OrderedDict()
        namespace = vars(renpy.store)

        for path, display, type_name in _vb_build_rows(scope, deep):
            try:
                value = eval(path, namespace, namespace)
            except Exception:
                continue

            old = base.get(path)

            if old is None:
                # A value missing from the baseline may just not have been
                # recorded (nested value in a shallow baseline, or a type the
                # baseline's view didn't cover). Only report variables that
                # really are new.
                if not _vb_type_ok(value, base_mode):
                    continue

                if base_deep or _vb_is_root_path(path):
                    result[path] = ("new", "new since baseline")

                continue

            result[path] = _vb_diff_entry(old, _vb_fingerprint(value))

        return result

    def _vb_get_diff(scope, deep):
        # path -> (kind, tag) for the rows in this view, against the current
        # baseline. Empty if there is no baseline.
        base, name, version, base_deep, base_mode = _vb_get_baseline()

        if not base:
            return collections.OrderedDict()

        key = (name, version, scope, bool(deep), _vb_state.type_mode)
        diff = _vb_state.diff_cache.get(key)

        if diff is None:
            diff = _vb_compute_diff(base, base_deep, base_mode, scope, deep)

            if len(_vb_state.diff_cache) > 8:
                _vb_state.diff_cache.clear()

            _vb_state.diff_cache[key] = diff

        return diff

    def _vb_matches_filter(entry, filt):
        if filt == "any":
            return True

        if entry is None:
            return False

        kind = entry[0]

        if filt == "changed":
            return kind != "same"

        if filt == "same":
            return kind == "same"

        return kind == filt

    def _vb_diff_color(entry):
        if entry is None:
            return "#ffffff"

        return _VB_DIFF_COLORS.get(entry[0], "#ffffff")

    def _vb_diff_summary(diff):
        mode = _vb_state.compare_mode

        if mode == "off":
            return "Change tracking is off."

        if not _vb_has_baseline():
            if mode == "snap":
                return "No snapshot yet. Press Take snapshot."

            return "No baseline yet: one is recorded each time you close the browser (or press Take snapshot)."

        counts = {"up": 0, "down": 0, "changed": 0, "new": 0}

        for entry in diff.values():
            if entry[0] in counts:
                counts[entry[0]] += 1

        label ="last close" if mode == "close" else "snapshot"

        return "vs %s: %d changed (%d up, %d down, %d other), %d new" % (
            label, counts["up"] + counts["down"] + counts["changed"],
            counts["up"], counts["down"], counts["changed"], counts["new"],
        )

    def _vb_capture(deep):
        # Fingerprint every variable (Store + Persistent; nested if deep).
        _vb_clear_cache()
        snap = collections.OrderedDict()
        namespace = vars(renpy.store)

        for path, display, type_name in _vb_build_rows("all", deep):
            try:
                snap[path] = _vb_fingerprint(eval(path, namespace, namespace))
            except Exception:
                pass

        return snap

    def _vb_take_snapshot(deep=False):
        try:
            snap = _vb_capture(bool(deep))
            _vb_state.snap = snap
            _vb_state.snap_deep = bool(deep)
            _vb_state.snap_mode = _vb_state.type_mode
            _vb_state.snap_version += 1
            _vb_state.compare_mode = "snap"
            _vb_clear_cache()
            _vb_state.status = (
                "Snapshot taken (%d values). Do something in the game, reopen the browser, "
                "then use Show: Changed / Unchanged / Up / Down." % len(snap)
            )
        except Exception as e:
            _vb_state.status = "ERROR: could not take snapshot: %s" % (e,)

        renpy.restart_interaction()

    def _vb_take_close_baseline():
        # Runs when the browser closes, so the next open can show what changed
        # in between. Never lets an error escape into the game.
        if not _VB_AUTO_BASELINE:
            return

        try:
            _vb_state.close_snap = _vb_capture(False)
            _vb_state.close_mode = _vb_state.type_mode
            _vb_state.close_version += 1
            _vb_clear_cache()
        except Exception:
            pass

    def _vb_set_compare(mode):
        _vb_state.compare_mode = mode
        renpy.restart_interaction()

    def _vb_set_filter(filt):
        _vb_state.diff_filter = filt
        renpy.restart_interaction()

    def _vb_cycle_types():
        # numbers -> flags -> all -> numbers
        order = ["numbers", "flags", "all"]
        current = _vb_state.type_mode
        index = order.index(current) if current in order else 1
        _vb_state.type_mode = order[(index + 1) % len(order)]
        renpy.restart_interaction()

    def _vb_types_label():
        return {
            "numbers": "Types: Numbers",
            "flags": "Types: Numbers + flags",
            "all": "Types: All",
        }.get(_vb_state.type_mode, "Types: All")

    def _vb_types_hint():
        mode = _vb_state.type_mode

        if mode == "numbers":
            return "Numbers only (int/float). Cycle Types to add True/False flags, or All (slower)."

        if mode == "flags":
            return "Numbers and True/False flags. Cycle Types for numbers only, or All (slower)."

        return ""

    def _vb_narrow(query, scope, deep):
        # Next scan: keep only the rows currently matching (search + Show
        # filter), then take a fresh snapshot to compare against next time.
        try:
            rows, total = _vb_collect_rows(query, scope, deep, None)
            _vb_state.candidates = frozenset([row[0] for row in rows])
            _vb_state.cand_version += 1
            _vb_state.diff_filter = "any"
            _vb_take_snapshot(deep)
            _vb_state.status = (
                "Narrowed to %d variables and took a new snapshot. Do something in the game, "
                "reopen, and filter again." % len(_vb_state.candidates)
            )
        except Exception as e:
            _vb_state.status = "ERROR: could not narrow: %s" % (e,)

        renpy.restart_interaction()

    def _vb_reset_narrowing():
        _vb_state.candidates = None
        _vb_state.cand_version += 1
        _vb_clear_cache()
        _vb_state.status = "Narrowing cleared."
        renpy.restart_interaction()

    def _vb_get_value(path):
        namespace = vars(renpy.store)
        return eval(path, namespace, namespace)

    def _vb_eval_node(node, namespace):
        expr = ast.Expression(body=node)
        ast.fix_missing_locations(expr)
        return eval(compile(expr, "<variable-browser>", "eval"), namespace, namespace)

    def _vb_resolve(path):
        # Split a path into (parent object, kind, key) so it can be assigned
        # without exec. kind is "name", "attr" or "item".
        namespace = vars(renpy.store)
        node = ast.parse(path.strip(), mode="eval").body

        if isinstance(node, ast.Name):
            return None, "name", node.id

        if isinstance(node, ast.Attribute):
            return _vb_eval_node(node.value, namespace), "attr", node.attr

        if isinstance(node, ast.Subscript):
            index = node.slice

            # Python 2 (and old Python 3) wrap plain subscripts in ast.Index.
            if not isinstance(index, ast.expr):
                index = getattr(index, "value", index)

            return (
                _vb_eval_node(node.value, namespace),
                "item",
                _vb_eval_node(index, namespace),
            )

        raise ValueError("Can't edit this path.")

    def _vb_assign(path, new_value):
        parent, kind, key = _vb_resolve(path)

        if kind == "name":
            setattr(renpy.store, key, new_value)
        elif kind == "attr":
            setattr(parent, key, new_value)
        else:
            if isinstance(parent, tuple):
                raise ValueError("Tuple items are read-only.")

            parent[key] = new_value

    def _vb_parse_value(text, current):
        raw = (text or "").strip()

        # Strings are made convenient: plain text stays plain text, quoted
        # text (including Python 2's u'...') is unquoted.
        if isinstance(current, _vb_string_types):
            try:
                value = ast.literal_eval(raw)
            except Exception:
                return raw

            if isinstance(value, _vb_string_types):
                if not isinstance(value, _vb_text_type):
                    value = value.decode("utf-8")
                return value

            return raw

        # Friendly boolean input.
        if isinstance(current, bool):
            low = raw.lower()

            if low in ("true", "1", "yes", "on"):
                return True

            if low in ("false", "0", "no", "off"):
                return False

            raise ValueError("Boolean must be True or False.")

        # For normal Python-ish values, use literal_eval.
        value = ast.literal_eval(raw)

        # Preserve numeric type, but don't silently truncate 12.7 to 12.
        if isinstance(current, _vb_int_types) and not isinstance(current, bool):
            if not isinstance(value, _vb_number_types):
                raise ValueError("Expected a whole number.")

            if isinstance(value, float) and value != int(value):
                raise ValueError("Expected a whole number (got %r)." % (value,))

            return int(value)

        if isinstance(current, float):
            if not isinstance(value, _vb_number_types):
                raise ValueError("Expected a number.")

            return float(value)

        # Keep the container class (e.g. Ren'Py's rollback-aware list/dict).
        for base in (list, dict, set):
            if isinstance(current, base) and isinstance(value, base) and not isinstance(value, type(current)):
                try:
                    value = type(current)(value)
                except Exception:
                    pass
                break

        return value

    # ------------------------------------------------------------------
    # Pins: saved per game in the save folder.
    # ------------------------------------------------------------------

    def _vb_pins_path():
        # Resolved lazily: config.savedir may not exist yet during init.
        base = getattr(config, "savedir", None) or getattr(config, "gamedir", None) or "."
        return _vb_os.path.join(base, _VB_PINS_FILENAME)

    def _vb_save_pins():
        # Returns "" on success or an error message.
        pins_data = []

        for pin in _vb_state.pins.values():
            pins_data.append({
                "path": pin.path,
                "note": pin.note,
                "mode": pin.mode,
                "limit": pin.limit_text,
            })

        try:
            text = _vb_json.dumps({"version": 1, "pins": pins_data}, indent=2, sort_keys=True)

            with open(_vb_pins_path(), "wb") as f:
                f.write(text.encode("utf-8"))

            return ""
        except Exception as e:
            return "%s" % (e,)

    def _vb_commit(message):
        # Save the pins file and report the outcome in the status line.
        err = _vb_save_pins()

        if err:
            message += "  (WARNING: could not save pins file: %s)" % (err,)

        _vb_state.status = message

    def _vb_ensure_pins_loaded():
        if _vb_state.pins_loaded:
            return

        _vb_state.pins_loaded = True
        path = _vb_pins_path()

        try:
            if not _vb_os.path.exists(path):
                return

            with open(path, "rb") as f:
                data = _vb_json.loads(f.read().decode("utf-8"))

            for item in data.get("pins", []):
                pin_path = item.get("path", "")

                if not pin_path or _vb_is_protected(pin_path) or not _vb_path_is_safe(pin_path):
                    continue

                pin = _VBPin(
                    pin_path,
                    item.get("note", ""),
                    item.get("mode", "off"),
                    item.get("limit", ""),
                )

                if pin.mode not in ("exact", "min", "max"):
                    pin.mode = "off"

                if pin.mode != "off":
                    try:
                        pin.value = _vb_literal(pin.limit_text)
                    except Exception:
                        pin.mode = "off"
                        pin.state = "saved lock value was unreadable"

                _vb_state.pins[pin_path] = pin

        except Exception as e:
            _vb_state.status = "WARNING: could not read pins file: %s" % (e,)

    def _vb_lock_short(pin):
        if pin.mode == "off":
            return ""

        prefix = {"exact": "= ", "min": ">= ", "max": "<= "}.get(pin.mode, "")
        text = "LOCK " + prefix + _vb_safe_repr(pin.value, 30)

        if not _vb_state.locks_enabled:
            text = "(paused) " + text

        if pin.state == "missing":
            text += " ?"

        return text

    def _vb_lock_description(pin):
        if pin is None or pin.mode == "off":
            return "not locked"

        names = {"exact": "Exactly ", "min": "At least ", "max": "At most "}
        text = names.get(pin.mode, "") + _vb_safe_repr(pin.value, 60)

        if not _vb_state.locks_enabled:
            text += "  (paused: Locks switch is Off)"

        if pin.state == "missing":
            text += "  (variable not found right now)"
        elif pin.state not in ("", "ok"):
            text += "  (%s)" % (pin.state,)

        return text

    def _vb_any_lock():
        for pin in _vb_state.pins.values():
            if pin.mode != "off":
                return True

        return False

    def _vb_pin_rows(query=""):
        # Rows for the Pins tab: (path, note, lock text, value text, type).
        _vb_ensure_pins_loaded()
        q = (query or "").strip().lower()
        rows = []
        base = _vb_get_baseline()[0]

        for path, pin in _vb_state.pins.items():
            try:
                value = _vb_get_value(path)
                value_text = _vb_safe_repr(value, 200)
                type_name = type(value).__name__

                # Mark pins that changed since the baseline.
                old = base.get(path) if base else None

                if old is not None:
                    kind, tag = _vb_diff_entry(old, _vb_fingerprint(value))

                    if kind != "same":
                        value_text += "   (%s)" % (tag,)
            except Exception:
                value_text = "<not available right now>"
                type_name = "?"

            lock_text = _vb_lock_short(pin)

            if q and q not in (path + " " + pin.note + " " + value_text + " " + lock_text).lower():
                continue

            rows.append((path, pin.note or "-", lock_text, value_text, type_name))

        return rows

    def _vb_pin(path):
        ok = False

        try:
            if not path:
                raise ValueError("Select a variable first.")

            if _vb_is_protected(path):
                raise ValueError("That variable is protected by the browser.")

            if not _vb_path_is_safe(path):
                raise ValueError("This path can't be pinned.")

            _vb_get_value(path)   # must exist right now

            if path in _vb_state.pins:
                _vb_state.status = "%s is already pinned." % (path,)
            else:
                _vb_state.pins[path] = _VBPin(path)
                _vb_commit("Pinned %s. Open the Pins tab to add a note or lock." % (path,))

            ok = True

        except Exception as e:
            _vb_state.status = "ERROR: %s" % (e,)

        if ok:
            _vb_load_selection(path)
        else:
            renpy.restart_interaction()

    def _vb_unpin(path):
        pin = _vb_state.pins.pop(path, None)

        if pin is not None:
            _vb_commit("Unpinned %s." % (path,))

        scope = _vb_get_scope()

        if scope is not None and scope.get("vb_tab") == "pins":
            scope["vb_selected"] = ""

        renpy.restart_interaction()

    def _vb_save_note(path, note):
        pin = _vb_state.pins.get(path)

        if pin is None:
            _vb_state.status = "ERROR: pin the variable first."
        else:
            pin.note = (note or "").strip()[:200]
            _vb_commit("Saved note for %s." % (path,))

        renpy.restart_interaction()

    # ------------------------------------------------------------------
    # Locks
    # ------------------------------------------------------------------

    def _vb_enforce_one(pin):
        # Returns True if it changed the variable.
        if pin.code is None:
            pin.code = compile(pin.path, "<variable-browser>", "eval")

        namespace = vars(renpy.store)

        try:
            current = eval(pin.code, namespace, namespace)
        except Exception:
            pin.state = "missing"
            return False

        needs_set = False
        new_value = None

        if pin.mode == "exact":
            if current != pin.value:
                needs_set = True
                new_value = _vb_copy.deepcopy(pin.value)
        else:
            if isinstance(current, bool) or not isinstance(current, _vb_number_types):
                pin.state = "value is not a number right now"
                return False

            if pin.mode == "min" and current < pin.value:
                needs_set = True
            elif pin.mode == "max" and current > pin.value:
                needs_set = True

            if needs_set:
                new_value = float(pin.value) if isinstance(current, float) else pin.value

        pin.state = "ok"

        if not needs_set:
            return False

        _vb_assign(pin.path, new_value)
        return True

    def _vb_enforce_locks():
        # Returns True if any variable was changed.
        if not _vb_state.locks_enabled:
            return False

        if not _vb_state.pins_loaded:
            _vb_ensure_pins_loaded()

        changed = False

        for pin in list(_vb_state.pins.values()):
            if pin.mode == "off":
                continue

            try:
                if _vb_enforce_one(pin):
                    changed = True
            except Exception as e:
                pin.state = "error: %s" % (e,)

        return changed

    def _vb_lock_tick_periodic():
        try:
            if _vb_enforce_locks():
                # Let visible screens show the corrected value.
                renpy.restart_interaction()
        except Exception:
            pass

    def _vb_lock_tick_interact():
        try:
            _vb_enforce_locks()
        except Exception:
            pass

    def _vb_set_locks(enabled):
        _vb_state.locks_enabled = bool(enabled)

        if enabled:
            _vb_ensure_pins_loaded()
            _vb_enforce_locks()
            _vb_state.status = "Locks are ON."
        else:
            _vb_state.status = "Locks are OFF (settings are kept)."

        renpy.restart_interaction()

    def _vb_set_lock(path, mode, text):
        ok = False

        try:
            pin = _vb_state.pins.get(path)

            if pin is None:
                raise ValueError("Pin the variable first.")

            if mode == "off":
                pin.mode = "off"
                pin.value = None
                pin.limit_text = ""
                pin.code = None
                pin.state = ""
                _vb_commit("Removed the lock from %s." % (path,))
            else:
                current = _vb_get_value(path)

                if (text or "").strip():
                    new_value = _vb_parse_value(text, current)
                else:
                    new_value = _vb_copy.deepcopy(current)

                if mode in ("min", "max"):
                    if isinstance(current, bool) or not isinstance(current, _vb_number_types):
                        raise ValueError("At least / At most only work on numbers.")

                    if isinstance(new_value, bool) or not isinstance(new_value, _vb_number_types):
                        raise ValueError("Enter a number for the limit.")

                limit_text, complete = _vb_edit_text(new_value)

                if not complete:
                    raise ValueError("That value is too large to lock.")

                pin.mode = mode
                pin.value = new_value
                pin.limit_text = limit_text
                pin.code = None
                pin.state = ""

                _vb_commit("Lock set on %s: %s." % (path, _vb_lock_description(pin)))

                if _vb_state.locks_enabled:
                    _vb_enforce_locks()

            ok = True

        except Exception as e:
            _vb_state.status = "ERROR: %s" % (e,)

        if ok:
            _vb_load_selection(path)
        else:
            renpy.restart_interaction()

    def _vb_use_current(path):
        scope = _vb_get_scope()

        try:
            text, complete = _vb_edit_text(_vb_get_value(path))

            if scope is not None:
                scope["vb_limit_value"] = text
        except Exception as e:
            _vb_state.status = "ERROR: %s" % (e,)

        renpy.restart_interaction()

    # ------------------------------------------------------------------
    # Selection / editing
    # ------------------------------------------------------------------

    def _vb_get_scope():
        screen = renpy.get_screen("variable_browser")
        return screen.scope if screen is not None else None

    def _vb_load_selection(path):
        # Called when a row is clicked (and after Apply): fills the edit area
        # with the live, full-length value.
        scope = _vb_get_scope()

        if scope is None:
            return

        pin = _vb_state.pins.get(path)
        found = True
        error = ""
        value = None
        parent = None
        kind = ""

        try:
            value = _vb_get_value(path)
            parent, kind, key = _vb_resolve(path)
        except Exception as e:
            found = False
            error = "%s" % (e,)

        # Note / lock fields for pinned variables.
        scope["vb_note_value"] = pin.note if pin is not None else ""
        scope["vb_limit_value"] = pin.limit_text if (pin is not None and pin.mode != "off") else ""
        scope["vb_lock_mode"] = pin.mode if (pin is not None and pin.mode != "off") else "exact"

        if not found:
            if pin is None:
                _vb_state.status = "ERROR: %s" % (error,)
            else:
                # Keep pins whose variable is missing selectable so they can
                # still be unpinned or have their note/lock edited.
                scope["vb_selected"] = path
                scope["vb_selected_type"] = "?"
                scope["vb_edit_value"] = ""
                scope["vb_edit_ok"] = False
                scope["vb_edit_note"] = "Variable not available right now (%s)." % (error,)

            renpy.restart_interaction()
            return

        text, complete = _vb_edit_text(value)
        editable = True
        note = ""

        if _vb_is_protected(path):
            editable = False
            note = "That variable is protected by the browser."
        elif kind == "item" and isinstance(parent, tuple):
            editable = False
            note = "Tuple items are read-only (tuples can't be changed in place)."
        elif not complete:
            editable = False
            note = "Value is too large to edit as text (over %d characters)." % _VB_MAX_EDIT

        scope["vb_selected"] = path
        scope["vb_selected_type"] = type(value).__name__
        scope["vb_edit_value"] = text
        scope["vb_edit_ok"] = editable
        scope["vb_edit_note"] = note

        renpy.restart_interaction()

    def _vb_apply_value(path, text):
        ok = False

        try:
            if not path:
                raise ValueError("Select a variable first.")

            if _vb_is_protected(path):
                raise ValueError("That variable is protected by the browser.")

            current = _vb_get_value(path)
            new_value = _vb_parse_value(text, current)
            _vb_assign(path, new_value)

            message = "Changed %s to %s" % (
                path,
                _vb_safe_repr(_vb_get_value(path), 220)
            )

            # An "Exactly" lock would immediately undo this edit, so move the
            # lock to the new value instead.
            pin = _vb_state.pins.get(path)

            if pin is not None and pin.mode == "exact":
                pin.value = _vb_copy.deepcopy(_vb_get_value(path))
                pin.limit_text = _vb_edit_text(pin.value)[0]
                _vb_save_pins()
                message += "  (Exactly lock moved to the new value)"

            # Make persistent changes hit disk as well.
            if path.startswith("persistent."):
                try:
                    renpy.save_persistent()
                except Exception as e:
                    message += "  (WARNING: could not save persistent data: %s)" % (e,)

            _vb_state.status = message
            ok = True

        except Exception as e:
            _vb_state.status = "ERROR: %s" % (e,)

        _vb_clear_cache()

        # On success show the stored value; on failure keep what was typed.
        if ok:
            _vb_load_selection(path)
        else:
            renpy.restart_interaction()

    def _vb_toggle():
        if renpy.get_screen("variable_browser"):
            renpy.hide_screen("variable_browser")
        else:
            # Always start from fresh values, not whatever was cached the
            # last time the browser was open.
            _vb_clear_cache()
            _vb_ensure_pins_loaded()
            renpy.show_screen("variable_browser")

        renpy.restart_interaction()

    # The hotkey lives in config.underlay so it also works outside the normal
    # in-game overlay (menus, hidden interface). The screen has its own key
    # binding to close itself while it is modal.
    config.keymap["variable_browser_toggle"] = [_VB_HOTKEY]
    config.underlay.append(renpy.Keymap(variable_browser_toggle=_vb_toggle))

    # Locks are re-applied while the game waits for input and at the start of
    # every interaction.
    config.periodic_callbacks.append(_vb_lock_tick_periodic)
    config.interact_callbacks.append(_vb_lock_tick_interact)


# Self-contained styling so the browser stays readable under any game theme.
style vb_text is default:
    font "DejaVuSans.ttf"
    color "#ffffff"
    size 18
    outlines []

style vb_button_text is vb_text:
    idle_color "#dddddd"
    hover_color "#ffffff"
    insensitive_color "#777777"

style vb_input is vb_text:
    color "#ffff99"

style vb_button is default:
    background Solid("#2f2f3a")
    hover_background Solid("#4a4a66")
    selected_background Solid("#5a5a88")
    insensitive_background Solid("#25252d")
    padding (8, 3)

style vb_frame is default:
    background Solid("#1b1b22")
    padding (8, 8)


screen variable_browser():
    modal True
    zorder 9999

    default vb_tab = "browse"
    default vb_query = ""
    default vb_scope = "all"
    default vb_deep = False
    default vb_limit = _VB_MAX_ROWS
    default vb_selected = ""
    default vb_selected_type = ""
    default vb_edit_value = ""
    default vb_edit_ok = False
    default vb_edit_note = ""
    default vb_note_value = ""
    default vb_limit_value = ""
    default vb_lock_mode = "exact"
    default vb_search_input = ScreenVariableInputValue("vb_query", default=True)
    default vb_edit_input = ScreenVariableInputValue("vb_edit_value", default=False)
    default vb_note_input = ScreenVariableInputValue("vb_note_value", default=False)
    default vb_limit_input = ScreenVariableInputValue("vb_limit_value", default=False)

    $ _vb_ensure_pins_loaded()
    $ vb_pins = _vb_state.pins
    $ vb_pin = vb_pins.get(vb_selected)
    $ vb_pin_count = len(vb_pins)

    # Scale to the game's resolution instead of assuming 1180x760.
    $ vb_w = min(1180, int(config.screen_width * 0.96))
    $ vb_h = min(760, int(config.screen_height * 0.96))
    $ vb_bot_h = 190 if vb_tab == "browse" else 290
    # Height left for the list = frame height - everything else in the vbox.
    $ vb_list_h = max(100, vb_h - (264 if vb_tab == "browse" else 194) - vb_bot_h)
    $ vb_has_base = _vb_has_baseline()
    $ vb_compare = _vb_state.compare_mode
    $ vb_filter = _vb_state.diff_filter
    $ vb_cands = _vb_state.candidates
    $ vb_c1 = int(vb_w * 0.35)
    $ vb_c2 = int(vb_w * 0.10)
    $ vb_c3 = int(vb_w * 0.45)
    $ vb_pc1 = int(vb_w * 0.22)
    $ vb_pc2 = int(vb_w * 0.22)
    $ vb_pc3 = int(vb_w * 0.16)
    $ vb_pc4 = int(vb_w * 0.28)

    key _VB_HOTKEY action Hide("variable_browser")
    key "K_ESCAPE" action Hide("variable_browser")

    # Record a baseline when the browser closes (used by "Last close").
    on "hide" action Function(_vb_take_close_baseline)

    add Solid("#000000b8")

    frame:
        style "vb_frame"
        xalign 0.5
        yalign 0.5
        xsize vb_w
        ysize vb_h
        padding (20, 18)

        vbox:
            spacing 10

            hbox:
                spacing 12

                text "Live Variable Browser" size 26 yalign 0.5

                textbutton "Browse":
                    style "vb_button"
                    text_style "vb_button_text"
                    selected vb_tab == "browse"
                    action SetScreenVariable("vb_tab", "browse")

                textbutton "Pins ([vb_pin_count])":
                    style "vb_button"
                    text_style "vb_button_text"
                    selected vb_tab == "pins"
                    action SetScreenVariable("vb_tab", "pins")

                null width 10

                if _vb_state.locks_enabled:
                    textbutton "Locks: On":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected True
                        action Function(_vb_set_locks, False)
                else:
                    textbutton "Locks: Off":
                        style "vb_button"
                        text_style "vb_button_text"
                        action Function(_vb_set_locks, True)

                textbutton "Close":
                    style "vb_button"
                    text_style "vb_button_text"
                    action Hide("variable_browser")

            hbox:
                spacing 10

                text "Search:" yalign 0.5

                button:
                    style "vb_button"
                    xsize int(vb_w * 0.22)
                    ysize 42
                    padding (8, 4)
                    action vb_search_input.Enable()
                    key_events True

                    input:
                        style "vb_input"
                        value vb_search_input
                        length 100
                        copypaste True

                if vb_tab == "browse":
                    textbutton "All":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_scope == "all"
                        action SetScreenVariable("vb_scope", "all")

                    textbutton "Store":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_scope == "store"
                        action SetScreenVariable("vb_scope", "store")

                    textbutton "Persistent":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_scope == "persistent"
                        action SetScreenVariable("vb_scope", "persistent")

                    if vb_deep:
                        textbutton "Deep: On":
                            style "vb_button"
                            text_style "vb_button_text"
                            action SetScreenVariable("vb_deep", False)
                    else:
                        textbutton "Deep: Off":
                            style "vb_button"
                            text_style "vb_button_text"
                            action SetScreenVariable("vb_deep", True)

                    $ vb_types_label = _vb_types_label()

                    textbutton "[vb_types_label]":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected _vb_state.type_mode != "all"
                        action Function(_vb_cycle_types)

                textbutton "Refresh":
                    style "vb_button"
                    text_style "vb_button_text"
                    action Function(_vb_refresh)

            if vb_tab == "browse":
                $ vb_rows, vb_total = _vb_collect_rows(vb_query, vb_scope, vb_deep, vb_limit)
                $ vb_shown = len(vb_rows)
                $ vb_diff = _vb_get_diff(vb_scope, vb_deep) if (vb_has_base and vb_compare != "off") else {}
                $ vb_summary = _vb_diff_summary(vb_diff)
                $ vb_cand_count = len(vb_cands) if vb_cands is not None else 0

                hbox:
                    spacing 8

                    text "Compare to:" size 16 yalign 0.5

                    textbutton "Last close":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_compare == "close"
                        action Function(_vb_set_compare, "close")

                    textbutton "Snapshot":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_compare == "snap"
                        sensitive _vb_state.snap is not None
                        action Function(_vb_set_compare, "snap")

                    textbutton "Off":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_compare == "off"
                        action Function(_vb_set_compare, "off")

                    null width 8

                    textbutton "Take snapshot":
                        style "vb_button"
                        text_style "vb_button_text"
                        action Function(_vb_take_snapshot, vb_deep)

                    textbutton "Narrow to shown":
                        style "vb_button"
                        text_style "vb_button_text"
                        sensitive vb_has_base
                        action Function(_vb_narrow, vb_query, vb_scope, vb_deep)

                    if vb_cands is not None:
                        textbutton "Reset narrowing":
                            style "vb_button"
                            text_style "vb_button_text"
                            action Function(_vb_reset_narrowing)

                hbox:
                    spacing 8

                    text "Show:" size 16 yalign 0.5

                    textbutton "Any":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_filter == "any"
                        action Function(_vb_set_filter, "any")

                    textbutton "Changed":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_filter == "changed"
                        action Function(_vb_set_filter, "changed")

                    textbutton "Unchanged":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_filter == "same"
                        action Function(_vb_set_filter, "same")

                    textbutton "Up":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_filter == "up"
                        action Function(_vb_set_filter, "up")

                    textbutton "Down":
                        style "vb_button"
                        text_style "vb_button_text"
                        selected vb_filter == "down"
                        action Function(_vb_set_filter, "down")

                    null width 8

                    text "[vb_summary!q]" size 15 yalign 0.5

                hbox:
                    spacing 14

                    if vb_total > vb_shown:
                        text "Showing [vb_shown] of [vb_total] rows." size 16 yalign 0.5

                        textbutton "Show more":
                            style "vb_button"
                            text_style "vb_button_text"
                            action SetScreenVariable("vb_limit", vb_limit + _VB_MAX_ROWS)
                    else:
                        text "[vb_total] rows.   * = pinned." size 16 yalign 0.5

                    $ vb_types_hint = _vb_types_hint()

                    if vb_types_hint:
                        text "[vb_types_hint!q]" size 16 yalign 0.5 color "#9cccff"

                    if vb_cands is not None:
                        text "Narrowed to [vb_cand_count] candidate variables." size 16 color "#9cccff"

                frame:
                    style "vb_frame"
                    background Solid("#14141a")
                    xfill True
                    ysize vb_list_h

                    viewport:
                        mousewheel True
                        draggable True
                        scrollbars "vertical"
                        pagekeys True

                        vbox:
                            spacing 3

                            for vb_path, vb_value, vb_type in vb_rows:
                                $ vb_label = ("* " + vb_path) if vb_path in vb_pins else vb_path
                                $ vb_entry = vb_diff.get(vb_path)
                                $ vb_col = _vb_diff_color(vb_entry)
                                $ vb_tag = vb_entry[1] if vb_entry is not None else ""

                                button:
                                    style "vb_button"
                                    xfill True
                                    selected vb_path == vb_selected

                                    action [
                                        Function(_vb_load_selection, vb_path),
                                        vb_edit_input.Enable(),
                                    ]

                                    hbox:
                                        spacing 12

                                        text "[vb_label!q]" xsize vb_c1 color vb_col
                                        text "[vb_type!q]" xsize vb_c2 size 16

                                        vbox:
                                            xsize vb_c3

                                            text "[vb_value!q]" xsize vb_c3 size 16

                                            if vb_tag:
                                                text "[vb_tag!q]" xsize vb_c3 size 15 color vb_col

            else:
                $ vb_pin_rows = _vb_pin_rows(vb_query)

                if not _vb_state.locks_enabled and _vb_any_lock():
                    text "Some pins have locks, but the Locks switch is Off. Click Locks: Off (top right) to enforce them." size 16
                else:
                    text "Pinned variables are saved per game. Select one to edit its value, note or lock. Refresh updates the values." size 16

                frame:
                    style "vb_frame"
                    background Solid("#14141a")
                    xfill True
                    ysize vb_list_h

                    if vb_pin_rows:
                        viewport:
                            mousewheel True
                            draggable True
                            scrollbars "vertical"
                            pagekeys True

                            vbox:
                                spacing 3

                                for vb_p_path, vb_p_note, vb_p_lock, vb_p_value, vb_p_type in vb_pin_rows:
                                    button:
                                        style "vb_button"
                                        xfill True
                                        selected vb_p_path == vb_selected

                                        action [
                                            Function(_vb_load_selection, vb_p_path),
                                            vb_edit_input.Enable(),
                                        ]

                                        hbox:
                                            spacing 12

                                            text "[vb_p_note!q]" xsize vb_pc1 color "#b8d8ff"
                                            text "[vb_p_path!q]" xsize vb_pc2 size 16
                                            text "[vb_p_lock!q]" xsize vb_pc3 size 16 color "#ffd080"
                                            text "[vb_p_value!q]" xsize vb_pc4 size 16
                    else:
                        text "No pinned variables yet. In the Browse tab, select a variable and press Pin." size 18

            frame:
                style "vb_frame"
                background Solid("#14141a")
                xfill True
                ysize vb_bot_h
                padding (10, 8)

                vbox:
                    spacing 7

                    if vb_selected:
                        text "Selected: [vb_selected!q]    ([vb_selected_type!q])" size 19

                        hbox:
                            spacing 10

                            button:
                                style "vb_button"
                                xsize vb_w - 330
                                ysize 42
                                padding (8, 4)
                                action vb_edit_input.Enable()
                                key_events True

                                input:
                                    style "vb_input"
                                    value vb_edit_input
                                    length _VB_MAX_EDIT
                                    copypaste True

                            textbutton "Apply":
                                style "vb_button"
                                text_style "vb_button_text"
                                yalign 0.5
                                sensitive vb_edit_ok
                                action Function(_vb_apply_value, vb_selected, vb_edit_value)

                            if vb_selected in vb_pins:
                                textbutton "Unpin":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    yalign 0.5
                                    action Function(_vb_unpin, vb_selected)
                            else:
                                textbutton "Pin":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    yalign 0.5
                                    action Function(_vb_pin, vb_selected)

                        if vb_tab == "pins" and vb_pin is not None:
                            hbox:
                                spacing 8

                                text "Note:" yalign 0.5 xsize 60

                                button:
                                    style "vb_button"
                                    xsize int(vb_w * 0.55)
                                    ysize 42
                                    padding (8, 4)
                                    action vb_note_input.Enable()
                                    key_events True

                                    input:
                                        style "vb_input"
                                        value vb_note_input
                                        length 200
                                        copypaste True

                                textbutton "Save note":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    yalign 0.5
                                    action Function(_vb_save_note, vb_selected, vb_note_value)

                            hbox:
                                spacing 8

                                text "Lock:" yalign 0.5 xsize 60

                                textbutton "Off":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    selected vb_lock_mode == "off"
                                    action SetScreenVariable("vb_lock_mode", "off")

                                textbutton "Exactly":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    selected vb_lock_mode == "exact"
                                    action SetScreenVariable("vb_lock_mode", "exact")

                                textbutton "At least":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    selected vb_lock_mode == "min"
                                    action SetScreenVariable("vb_lock_mode", "min")

                                textbutton "At most":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    selected vb_lock_mode == "max"
                                    action SetScreenVariable("vb_lock_mode", "max")

                                button:
                                    style "vb_button"
                                    xsize int(vb_w * 0.15)
                                    ysize 42
                                    padding (8, 4)
                                    action vb_limit_input.Enable()
                                    key_events True

                                    input:
                                        style "vb_input"
                                        value vb_limit_input
                                        length 2000
                                        copypaste True

                                textbutton "Set lock":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    yalign 0.5
                                    action Function(_vb_set_lock, vb_selected, vb_lock_mode, vb_limit_value)

                                textbutton "Use current":
                                    style "vb_button"
                                    text_style "vb_button_text"
                                    yalign 0.5
                                    action Function(_vb_use_current, vb_selected)

                            $ vb_lock_text = _vb_lock_description(vb_pin)
                            text "Current lock: [vb_lock_text!q]    (blank value = use current value)" size 16

                        if vb_edit_note:
                            text "[vb_edit_note!q]" size 16
                        elif vb_selected.startswith("persistent."):
                            text "WARNING: persistent.* changes are saved to disk and can affect future sessions." size 16
                        elif vb_tab == "browse":
                            text "Examples: 999   12.5   True   False   None   \"hello\"   [[1, 2, 3]" size 16

                    else:
                        text "Select a variable above, then its editable value appears here." size 18

                    if _vb_state.status:
                        text "[_vb_state.status!q]" size 16
