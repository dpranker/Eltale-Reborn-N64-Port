#!/usr/bin/env python3
"""Maps a crash PC to a game function, or to a mod's module and function, or a runtime or trampoline address.

usage: addr2mod.py <rom build dir> <address>...   e.g. addr2mod.py build/rom/eltale-test 0x80404d38
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import nrm_inspect as ni

ROOT = Path(__file__).resolve().parent.parent
MAPS = {
    "quest64_modern_gameplay": ROOT / "vendor/Eltale-Reborn-DC-Port/eltale/quest64_modern_gameplay.map",
    "eltale_reborn": ROOT / "vendor/Eltale-Reborn-DC-Port/eltale/eltale_reborn.map",
}


class MapOnly:
    """The fields the map parser and locate() need, for a mod whose binary isn't loaded here."""

    def __init__(self, entry):
        self.name = entry["id"]
        self.vram, self.size, self.bss = ni.MOD_BASE, entry["size"], entry["bss"]


def describe(address, layout, by_vram):
    for entry in layout["mods"]:
        if entry["base"] <= address < entry["base"] + entry["size"] + entry["bss"]:
            offset = address - entry["base"]
            path = MAPS.get(entry["id"])
            if path is None:
                return f"{entry['id']} +{offset:#x} (no link map)"
            mod = MapOnly(entry)
            ni.parse_map(path, mod)
            module, symbol = ni.locate(mod, ni.MOD_BASE + offset)
            return f"{entry['id']} {module}: {symbol} (binary offset {offset:#x})"
    if layout["stubs"] <= address < layout["runtime"]:
        return "import stub"
    if layout["trampolines"] <= address < layout["image_end"]:
        return f"trampoline +{address - layout['trampolines']:#x}"
    if layout["runtime"] <= address < layout["trampolines"]:
        best = max(((v, k) for k, v in layout["runtime_symbols"].items() if v <= address), default=None)
        return f"runtime {best[1]} +{address - best[0]:#x}" if best else "runtime"
    matches = [f for funcs in by_vram.values() for f in funcs if f.vram <= address < f.vram + f.size]
    if matches:
        return " or ".join(f"{f.name} +{address - f.vram:#x} ({f.section['name']})" for f in matches)
    return "not in code"


def main():
    layout = json.loads((Path(sys.argv[1]) / "layout.json").read_text())
    _, _, _, by_vram = ni.load_game_funcs()
    for text in sys.argv[2:]:
        address = int(text, 16)
        print(f"{address:#010x}: {describe(address, layout, by_vram)}")


if __name__ == "__main__":
    main()
