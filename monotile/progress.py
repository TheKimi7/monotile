"""A one-line progress bar for long conversions, shown only in a terminal.

    Monotile-Circle-Dark   ██████████░░░░░░░░░░  52%  2,280/4,379  ~2 min left

In logs and the background watcher (no terminal) it stays silent.
"""
import shutil
import sys
import time


class Bar:
    def __init__(self, label, total, stream=None):
        self.label, self.total = label, total
        self.stream = stream or sys.stdout
        self.live = total > 0 and hasattr(self.stream, "isatty") and self.stream.isatty()
        self.start = time.monotonic()
        self.last = 0.0
        self.done = 0
        longest = len(f" 100%  {total:,}/{total:,}  ~99 min left")
        cols = shutil.get_terminal_size((80, 20)).columns
        self.width = max(10, min(30, cols - len(label) - longest - 6))
        if self.live:
            self._draw()

    def step(self, n=1):
        self.done += n
        now = time.monotonic()
        if self.live and (now - self.last >= 0.1 or self.done >= self.total):
            self.last = now
            self._draw()

    def close(self):
        if self.live:
            self.done = self.total
            self._draw()
            self.stream.write("\n")
            self.stream.flush()

    def _draw(self):
        frac = min(1.0, self.done / self.total)
        left = ""
        elapsed = time.monotonic() - self.start
        if 0.02 < frac < 1.0 and elapsed > 3:
            secs = elapsed / frac - elapsed
            left = f"  ~{round(secs / 60)} min left" if secs >= 90 else f"  ~{max(1, round(secs))} s left"
        elif frac >= 1.0:
            left = f"  done in {round(elapsed)} s"
        tail = f" {round(frac * 100):3d}%  {self.done:,}/{self.total:,}{left}"
        cols = shutil.get_terminal_size((80, 20)).columns
        filled = round(frac * self.width)
        line = f"  {self.label}  {'█' * filled}{'░' * (self.width - filled)}{tail}"
        self.stream.write("\r" + line[:cols - 1].ljust(cols - 1))
        self.stream.flush()


def note(text, stream=None):
    """A status line shown only in a terminal (e.g. while scanning before a bar starts)."""
    stream = stream or sys.stdout
    if hasattr(stream, "isatty") and stream.isatty():
        stream.write(f"  {text}\n")
        stream.flush()
