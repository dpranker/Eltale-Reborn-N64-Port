# Frame times while moving through Melrode, where standing still flatters the numbers. The Dreamcast port's notes put
# the side streets and a turning camera as the worst cases. Walks go down the street first: up runs into the inn door.
gdb.execute("source tests/gdb/perf_common.py")


def walk(name, legs):
    """Each leg is a stick position and a number of frames. Skips the row if a scene or a door interrupted the walk."""
    melrode_street()
    reset()
    for stick, frames in legs:
        hold(stick=stick, frames=frames)
    moved = read32(NEXT_MAP) == 0 and read32(NEXT_ROOM) == 0 and free()
    check(moved, f"{name} stayed on the street, in free movement")
    report(name)


def circle(frames_per_turn, turns):
    """Walks in a circle, which swings the camera behind Brian all the way round."""
    steps = 16
    legs = []
    for i in range(steps * turns):
        angle = 2 * math.pi * i / steps
        legs.append(((int(70 * math.sin(angle)), int(70 * math.cos(angle))), frames_per_turn // steps))
    return legs


if TARGET == "eltale":
    title_to_new_game()
    talk(6000)
    set_flag(16)
else:
    new_game()
clear_scene()

walk("walk_street", [((0, -70), 150), ((0, 70), 135)])
walk("walk_west", [((0, -70), 45), ((-70, 0), 150), ((70, 0), 135)])
walk("walk_east", [((0, -70), 45), ((70, 0), 150), ((-70, 0), 135)])
walk("turning_circles", [((0, -70), 90)] + circle(96, 3))    # Away from the inn door first.
check(not faults, "no CPU faults")
finish()
