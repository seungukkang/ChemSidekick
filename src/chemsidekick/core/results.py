"""Recent results (kept automatically) and saved results (kept on request).

Every run gets a numbered folder in the recent-results store:

    ~/Library/Caches/ChemSidekick/recent/00012-element/
        run.json        input, result, tool ID, version, timing
        ...             files the tool wrote (SVG, SDF, XYZ, ...)

Only the newest `recent_limit` (default 50) are kept. macOS treats
~/Library/Caches as disposable and excludes it from backups.

`save()` copies one result to the save folder (default ~/Documents/ChemSidekick).
"""

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from chemsidekick import __version__
from chemsidekick.core.registry import ToolSpec
from chemsidekick.core.schemas import ToolResult

DEFAULT_ROOT = Path("~/Library/Caches/ChemSidekick/recent").expanduser()
RUN_FILE = "run.json"


def default_root() -> Path:
    """The store location; CSK_CACHE_DIR overrides it (used by tests)."""
    env = os.environ.get("CSK_CACHE_DIR")
    return Path(env).expanduser() if env else DEFAULT_ROOT


@dataclass(frozen=True)
class RecentEntry:
    number: int
    tool: str
    tool_id: str
    created: datetime
    answer: str
    path: Path

    def load(self) -> dict[str, Any]:
        return json.loads((self.path / RUN_FILE).read_text(encoding="utf-8"))


def _relative_artifacts(result: ToolResult, folder: Path) -> ToolResult:
    """Store artifact paths relative to the result folder, so a saved copy still works."""
    artifacts = []
    for a in result.artifacts:
        path = a.path
        if path.is_absolute() and path.is_relative_to(folder):
            path = path.relative_to(folder)
        artifacts.append(a.model_copy(update={"path": path}))
    return result.model_copy(update={"artifacts": artifacts})


class RecentStore:
    def __init__(self, root: Path | None = None, limit: int = 50) -> None:
        self.root = root or default_root()
        self.limit = limit

    # -- writing ------------------------------------------------------------

    def new_folder(self, tool_name: str) -> tuple[int, Path]:
        """Create the folder for a new run and return (number, folder)."""
        self.root.mkdir(parents=True, exist_ok=True)
        number = self._max_number() + 1
        while True:
            folder = self.root / f"{number:05d}-{tool_name}"
            try:
                folder.mkdir()
                return number, folder
            except FileExistsError:  # another process took this number
                number += 1

    def record(
        self,
        number: int,
        folder: Path,
        spec: ToolSpec,
        inp: BaseModel,
        result: ToolResult,
        *,
        elapsed_s: float,
        peak_memory_mb: float | None,
    ) -> RecentEntry:
        created = datetime.now().astimezone()
        run = {
            "number": number,
            "tool": spec.name,
            "tool_id": spec.id,
            "chemsidekick_version": __version__,
            "created": created.isoformat(timespec="seconds"),
            "elapsed_s": round(elapsed_s, 3),
            "peak_memory_mb": peak_memory_mb,
            "input": inp.model_dump(mode="json"),
            "result": _relative_artifacts(result, folder).model_dump(mode="json"),
        }
        (folder / RUN_FILE).write_text(
            json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        self.prune()
        return RecentEntry(number, spec.name, spec.id, created, result.answer, folder)

    def discard(self, folder: Path) -> None:
        """Remove the folder of a run that failed."""
        shutil.rmtree(folder, ignore_errors=True)

    def prune(self) -> None:
        """Keep only the newest `limit` results."""
        folders = sorted(self._folders(), key=lambda pair: pair[0])
        for _, folder in folders[: max(0, len(folders) - self.limit)]:
            shutil.rmtree(folder, ignore_errors=True)

    # -- reading ------------------------------------------------------------

    def entries(self) -> list[RecentEntry]:
        """Finished results, newest first."""
        out = []
        for _, folder in sorted(self._folders(), key=lambda pair: -pair[0]):
            run_file = folder / RUN_FILE
            if not run_file.exists():
                continue
            run = json.loads(run_file.read_text(encoding="utf-8"))
            out.append(
                RecentEntry(
                    number=run["number"],
                    tool=run["tool"],
                    tool_id=run["tool_id"],
                    created=datetime.fromisoformat(run["created"]),
                    answer=run["result"]["answer"],
                    path=folder,
                )
            )
        return out

    def get(self, number: int | None = None) -> RecentEntry:
        """One result; the newest if `number` is None."""
        entries = self.entries()
        if not entries:
            raise LookupError("There are no recent results yet.")
        if number is None:
            return entries[0]
        for e in entries:
            if e.number == number:
                return e
        raise LookupError(
            f"Result #{number} is not in the recent results "
            f"(only the newest {self.limit} are kept). Run `csk recent` to see them."
        )

    # -- saving -------------------------------------------------------------

    def save(self, number: int | None, save_root: Path) -> Path:
        """Copy one result to <save_root>/<tool>/<YYYYMMDD-HHMMSS>/ and return the path."""
        entry = self.get(number)
        base = save_root / entry.tool / entry.created.strftime("%Y%m%d-%H%M%S")
        dest, n = base, 2
        while dest.exists():
            dest = base.with_name(f"{base.name}-{n}")
            n += 1
        shutil.copytree(entry.path, dest)
        return dest

    # -- helpers ------------------------------------------------------------

    def _folders(self) -> list[tuple[int, Path]]:
        if not self.root.exists():
            return []
        out = []
        for p in self.root.iterdir():
            head, _, _ = p.name.partition("-")
            if p.is_dir() and head.isdigit():
                out.append((int(head), p))
        return out

    def _max_number(self) -> int:
        return max((n for n, _ in self._folders()), default=0)
