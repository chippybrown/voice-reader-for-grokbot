# Where the toolbar controls sit for a given window size.
# No Tk here, so the wrapping rules can be tested without a display.

MIN_W = 72
MIN_H = 72
DEFAULT_W = 460
DEFAULT_H = 78
# Wide enough for the title, the status, and one row of playback buttons.
WIDE = 360
HEADER_WIDE = 30
HEADER_NARROW = 48
CELL = 40
PAD = 8
TRANSPORT = ("back", "stop", "pause", "play", "next")
CORNER = ("gear", "power")


def _cols(width, count):
    room = max(CELL, int(width) - PAD * 2)
    return max(1, min(count, room // CELL))


def min_height(width):
    """Shortest window that still fits the controls at this width."""
    width = max(MIN_W, int(width))
    if width >= WIDE:
        return HEADER_WIDE + CELL + PAD
    rows = (len(TRANSPORT) + len(CORNER) + _cols(width, len(TRANSPORT) + len(CORNER)) - 1) // _cols(width, len(TRANSPORT) + len(CORNER))
    return max(MIN_H, HEADER_NARROW + rows * CELL + PAD)


def clamp_size(width, height):
    """Grow a too-small drag so the buttons still fit."""
    width = max(MIN_W, int(width))
    height = max(min_height(width), int(height))
    return width, height


def clamp_origin(x, y, width, height, screen_w, screen_h):
    """Keep a slice of the window on the screen."""
    width, height = clamp_size(width, height)
    screen_w = max(width, int(screen_w or width))
    screen_h = max(height, int(screen_h or height))
    x = min(max(int(x), 8 - width), screen_w - 24)
    y = min(max(int(y), 0), screen_h - 24)
    return x, y


def _row(names, width, top, radius):
    """Center names on one horizontal line. Returns (name, x, y, r)."""
    span = CELL * len(names) - (CELL - radius * 2)
    left = max(PAD + radius, (width - span) // 2 + radius)
    y = top + radius
    return [(name, left + index * CELL, y, radius) for index, name in enumerate(names)]


def _wrap(names, width, top, radius):
    cols = _cols(width, len(names))
    span = CELL * cols - (CELL - radius * 2)
    left = max(PAD + radius, (width - span) // 2 + radius)
    placed = []
    for index, name in enumerate(names):
        col = index % cols
        row = index // cols
        placed.append((name, left + col * CELL, top + radius + row * CELL, radius))
    return placed


def arrange(width, height):
    """Title point, status point, and button centers for this window.

    A wide window keeps playback on one row and the gear and power on the
    title line. A narrower window wraps those buttons, and a skinny window
    stacks them.
    """
    width, height = clamp_size(width, height)
    if width >= WIDE:
        buttons = _row(TRANSPORT, width, HEADER_WIDE + 4, 15)
        buttons.append(("gear", width - 50, 17, 11))
        buttons.append(("power", width - 22, 17, 11))
        return {
            "width": width,
            "height": height,
            "title": (16, 16),
            "status": (250, 16),
            "buttons": buttons,
        }
    buttons = _wrap(TRANSPORT + CORNER, width, HEADER_NARROW, 15)
    return {
        "width": width,
        "height": height,
        "title": (12, 14),
        "status": (12, 34),
        "buttons": buttons,
    }
