"""Account-wide watch-reward credits shared by every room worker.

Bilibili settles the daily watch task one room at a time: with several rooms
open, each room waits its turn, and a single room can stay flat for well over
half an hour while the account is still being credited elsewhere. A per-room
stall therefore proves nothing on its own. This clock lets every worker see
whether the account as a whole is still earning, and how many turns this room
has been passed over.
"""

import time
from ..runtime import update_json


class CreditClock:
    """Persist observed watch-task credits for one account under a file lock."""

    def __init__(self, root, key, clock=time.time):
        self.path = root / "state" / f"watch-credit-{key}.json"
        self.clock = clock

    def observe(self, room, day, current):
        """Record this room's progress and return the account-wide view.

        The first observation of a room only establishes its baseline: a value
        already present when a worker starts is not evidence of a fresh credit.
        """
        now = self.clock()
        view = {}

        def change(value):
            if not isinstance(value, dict) or value.get("day") != day:
                value = {"day": day, "credits": 0, "rooms": {}}
            rooms = value.get("rooms")
            if not isinstance(rooms, dict):
                rooms = value["rooms"] = {}
            credits = value.get("credits")
            credits = credits if isinstance(credits, int) and credits >= 0 else 0
            entry = rooms.get(str(room))
            if not isinstance(entry, dict) or not isinstance(entry.get("current"), int):
                rooms[str(room)] = {"current": current, "at": now, "seen": credits}
            elif current > entry["current"]:
                credits += 1
                value["credits"] = credits
                value["last_credit_at"] = now
                value["last_credit_room"] = room
                rooms[str(room)] = {"current": current, "at": now, "seen": credits}
            elif current < entry["current"]:
                # Rollback or target change: rebase without counting a credit.
                rooms[str(room)] = {"current": current, "at": now, "seen": credits}
            view.update(value)
            return value

        update_json(self.path, change, {})
        entry = (view.get("rooms") or {}).get(str(room)) or {}
        last = view.get("last_credit_at")
        last = last if isinstance(last, (int, float)) and not isinstance(last, bool) else None
        credits = view.get("credits")
        credits = credits if isinstance(credits, int) and credits >= 0 else 0
        seen = entry.get("seen")
        seen = seen if isinstance(seen, int) and seen >= 0 else credits
        return {
            "seconds_since_credit": None if last is None else max(0, now - last),
            "last_credit_room": view.get("last_credit_room"),
            "pass_overs": max(0, credits - seen),
            "credits": credits,
        }
