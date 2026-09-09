import json
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "turn_logs.jsonl"


class TurnLogRepository:
    """Append-only JSONL store for turn logs -- the evaluation dataset.

    Treated as a deliverable, not debug output: never truncated or rewritten,
    only appended to.
    """

    def __init__(self, path: Path = DEFAULT_LOG_PATH) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        with self._path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def read_all(self, learner_id: str) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        records = []
        with self._path.open() as f:
            for line in f:
                record = json.loads(line)
                if record["learner_id"] == learner_id:
                    records.append(record)
        return records
