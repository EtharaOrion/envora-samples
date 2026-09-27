# Use synchronized output updates when the terminal supports them

## Description

I want the program to stop flickering on terminals that can draw a frame atomically. Right now
every screen update is written with the text cursor hidden first and shown again afterwards,
unconditionally - the portable fallback, and the only technique the renderer knows. Modern
terminals implement synchronized output (mode 2026), which lets the whole update be marked as one
atomic batch so nothing half-drawn is ever displayed, but the program never asks whether that
mode is available and has no way to receive the answer, so it can never use it. The renderer also
pushes each piece of an update straight to the output stream as it is produced, so even if the
answer arrived there is no point at which a complete update could be wrapped in anything. On top
of that, the shared terminal-rendering library this program is built on has moved on: at the
commit checked out beside this repository its renderer has withdrawn some of the terminal-state
bookkeeping it used to do on its caller's behalf, and reshaped one entry point, so the current
code will not even build against it.

## Expected Behavior

- On start-up the program asks the terminal whether synchronized output is supported, but only
  for terminals where that answer is trustworthy - not, for example, over a remote session on a
  terminal that has not identified itself.
- The reply from the terminal arrives as a message the program can handle, alongside the other
  terminal capability replies it already understands, and enabling the feature is a decision the
  program makes when that reply says the mode exists and is currently off.
- When synchronized output is in use, a screen update is emitted as one batch bracketed by the
  begin and end markers for the mode, and the cursor is not hidden and shown around it.
- When it is not in use, an update is still bracketed by hiding the text cursor and showing it
  again - but only around a real screen update, and only when the frame before it had a visible
  cursor: the hide goes before the update's bytes and the show after them. The write that restores
  the terminal on the way out is not bracketed at all.
- Alternate-screen entry and exit, text-cursor visibility and inline-versus-fullscreen positioning
  are driven by the program itself rather than delegated, and each is emitted only when the view
  actually changes it - no redundant repeats on unchanged updates.
- When one update both changes the alternate screen and re-applies text-cursor visibility, the
  alternate-screen sequence is written first and the cursor-visibility sequence after it.
- On the way out, moving to the last line and erasing below it emits the cursor move and the erase
  and nothing else - no extra carriage return alongside the move.
- Default to asking: withhold the start-up query only for terminals you have positive reason to
  distrust, and issue it through the same deferred output path the program already uses for its
  other terminal requests, ahead of the model's own initial commands.
- Everything that worked before keeps working: the program still runs end to end and still restores
  the terminal on exit. The exact byte stream on a terminal without the new mode does change - the
  redundant repeats above disappear - but what the user sees does not.

The terminal-rendering library this program depends on is checked out read-only at
`ultraviolet`; read it to learn which pieces of terminal state its renderer no longer
owns, and how a frame must now be handed to it, because the released module version this
repository currently requires still exposes the old contract and cannot tell you.

The repository is at `bubbletea`, checked out at commit
`8f17c3584f3df68f12703cb0f5e58f482f2e5d62`.

---

## Workspace

The following repositories are pre-installed in your workspace and available for import:

| Repository | Path |
|---|---|
| `charmbracelet/bubbletea` | `bubbletea` |
| `charmbracelet/ultraviolet` | `ultraviolet` |

Consult `ultraviolet` to determine the exact definitions the target expects. Do not modify anything under those checkouts, and do not edit tests or fixtures.
