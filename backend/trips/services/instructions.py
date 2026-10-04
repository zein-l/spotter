"""Turn OSRM maneuvers into English driving directions (OSRM returns no text itself)."""

from __future__ import annotations

import re

DIRECTIONS = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")


def normalize_ref(ref: str | None) -> str:
    """'I 55;US 66' -> 'I-55/US-66'."""
    if not ref:
        return ""
    parts = [re.sub(r"^([A-Za-z]+)\s+(\d)", r"\1-\2", p.strip()) for p in ref.split(";") if p.strip()]
    return "/".join(dict.fromkeys(parts))


def road_label(name: str | None, ref: str | None) -> str:
    """Highway number first, the way drivers read signs: 'I-55 (Stevenson Expressway)'."""
    name, ref = (name or "").strip(), normalize_ref(ref)
    if ref and name and ref.replace("-", " ") not in name:
        return f"{ref} ({name})"
    return ref or name


def short_road(name: str | None, ref: str | None) -> str:
    """Compact road name for remarks: 'I-44' rather than 'I-44 (Will Rogers Turnpike)'."""
    return normalize_ref(ref).split("/")[0] or (name or "").strip()


def osrm_instruction(step: dict, destination: str) -> str:
    maneuver = step.get("maneuver", {})
    kind = maneuver.get("type", "")
    modifier = maneuver.get("modifier", "") or ""
    road = road_label(step.get("name"), step.get("ref"))
    onto = f" onto {road}" if road else ""
    side = "left" if "left" in modifier else "right" if "right" in modifier else ""

    if kind == "depart":
        heading = DIRECTIONS[round(maneuver.get("bearing_after", 0) / 45) % 8]
        return f"Head {heading}" + (f" on {road}" if road else "")
    if kind == "arrive":
        return f"Arrive at {destination}" + (f", on the {side}" if side else "")
    if kind in ("turn", "end of road"):
        if modifier == "uturn":
            return f"Make a U-turn{onto}"
        if modifier == "straight":
            return f"Continue straight{onto}"
        prefix = "At the end of the road, turn" if kind == "end of road" else "Turn"
        return f"{prefix} {modifier or side}{onto}".replace("  ", " ")
    if kind == "continue":
        if modifier == "uturn":
            return f"Make a U-turn{onto}"
        if modifier in ("", "straight"):
            return f"Continue straight{onto}"
        return f"Continue {modifier}{onto}"
    if kind == "merge":
        return f"Merge{' ' + side if side else ''}{onto}"
    if kind == "on ramp":
        return f"Take the ramp{' on the ' + side if side else ''}{onto}"
    if kind == "off ramp":
        exits, toward = step.get("exits"), step.get("destinations")
        text = f"Take exit {exits.split(';')[0]}" if exits else "Take the exit"
        if side:
            text += f" on the {side}"
        if toward:
            text += f" toward {toward.split(',')[0].split(':')[-1].strip()}"
        elif road:
            text += onto
        return text
    if kind == "fork":
        return f"Keep {side or 'straight'} at the fork{onto}"
    if kind in ("roundabout", "rotary"):
        exit_number = maneuver.get("exit")
        if exit_number:
            return f"Enter the roundabout and take the {_ordinal(exit_number)} exit{onto}"
        return f"Enter the roundabout{onto}"
    if kind == "roundabout turn":
        return f"At the roundabout, turn {modifier or side}{onto}"
    if kind in ("exit roundabout", "exit rotary"):
        return f"Exit the roundabout{onto}"
    return f"Continue{onto}"  # "new name", "notification", "use lane" and unknown types


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
