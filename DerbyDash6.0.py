"""
Derby Dash — First-Person Risk/Reward Runner
============================================
A Python/Pygame game where the player is a jockey riding a horse through an
obstacle course. Before the race the player visits a bar and chooses up to 10
drinks. Each drink adds a score multiplier bonus but also stacks a gameplay
penalty (blur, wobble, speed-up, or input delay), creating a risk/reward trade-
off: drink more for a higher score, but the game gets progressively harder.

State machine:  BAR  →  CUTSCENE  →  RACE  →  GAME OVER  (→ BAR again)

Install:  pip install pygame
Run:      python derby_dash.py

Derby Dash — First-Person Risk/Reward Runner
============================================
Course project implementation in Python + Pygame.

Install:  pip install pygame
Run:      python derby_dash.py

Controls
--------
BAR PHASE:
  LEFT / RIGHT   — browse drinks
  ENTER / SPACE  — add selected drink
  BACKSPACE      — remove last drink
  R              — start the race

RACE PHASE:
  LEFT / RIGHT   — switch lane
  UP             — jump  (clears fences, hay, hurdles)
  DOWN (hold)    — duck  (clears barriers)
"""

import pygame
import os
import sys
import math
import random

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
#  All game-wide settings live here so they're easy to tweak in one place.
# ─────────────────────────────────────────────────────────────────────────────

# Window dimensions (pixels) and target frame rate.
W, H = 1280, 720
FPS  = 60
TITLE = "DERBY DASH"

# ── Named colours used repeatedly throughout the drawing code ────────────────
# Keeping them here avoids magic RGB tuples buried deep in draw calls.
C_BG        = (10, 5, 0)
C_SKY_TOP   = (13, 27, 42)
C_SKY_BOT   = (26, 58, 92)
C_GRASS     = (18, 52, 10)
C_GRASS2    = (14, 40, 8)
C_TRACK     = (90, 75, 50)
C_TRACK2    = (80, 65, 42)
C_WHITE     = (240, 230, 200)
C_GOLD      = (212, 160, 23)
C_DARK_GOLD = (139, 105, 20)
C_RED       = (192, 57,  43)
C_GREEN     = (39,  174, 96)
C_BLUE      = (52,  152, 219)
C_DARK      = (20, 10, 0)
C_PANEL     = (16, 8, 0)
C_WOOD      = (61, 31, 0)
C_WOOD2     = (92, 46, 0)

# ── Perspective / track layout ───────────────────────────────────────────────
# HORIZON_Y is the pixel row where the track vanishes to a point (the
# "camera" level). GROUND_Y is the bottom of the screen — the player's feet.
# LANE_FEET_X gives the screen-X centre of each of the 3 lanes at the
# player's position (depth = 0). All perspective maths derives from these.
HORIZON_Y   = 240       # pixel row of vanishing point
GROUND_Y    = H         # pixel row at player's feet
LANE_COUNT  = 3
# At depth=0 (feet) the three lane centres in screen-X
LANE_FEET_X = [W * 0.18, W * 0.50, W * 0.82]

# ── Collision window ─────────────────────────────────────────────────────────
# Obstacles are only checked for collision when their depth is in this range,
# i.e. when they are right in front of the player (depth 0 = player position).
HIT_DEPTH_MIN = 0.00
HIT_DEPTH_MAX = 0.13

# ─────────────────────────────────────────────────────────────────────────────
#  DRINKS CATALOGUE
#  Each entry is a dict describing one drink available at the bar.
#
#  Fields:
#    name     — display name shown on the drink card
#    emoji    — rendered on the card if the OS font supports it
#    symbol   — single-char fallback if emoji font is unavailable
#    mult_add — score multiplier bonus added per drink of this type.
#               Final multiplier = 1.0 + sum of all mult_add values ordered.
#               Max possible: 10 × vodka = 1 + 10*0.3 = ×4.0
#    blur     — stacks beer's vision-blur effect (1 unit per beer)
#    wobble   — stacks cider's screen-sway / stumble effect
#    speed    — stacks whiskey's game-speed bonus (obstacles come faster)
#    delay    — stacks vodka's input-delay penalty (controls respond late)
#    color    — RGB used for card highlight and HUD pill
# ─────────────────────────────────────────────────────────────────────────────
DRINKS = [
    dict(name="WATER",   emoji="💧", symbol="~", mult_add=0.00,
         blur=0, wobble=0, speed=0, delay=0, color=(126, 200, 227)),
    dict(name="BEER",    emoji="🍺", symbol="B", mult_add=0.05,
         blur=1, wobble=0, speed=0, delay=0, color=(240, 165,   0)),
    dict(name="CIDER",   emoji="🍎", symbol="C", mult_add=0.10,
         blur=0, wobble=1, speed=0, delay=0, color=(192,  57,  43)),
    dict(name="WHISKEY", emoji="🥃", symbol="W", mult_add=0.20,
         blur=0, wobble=0, speed=1, delay=0, color=(139,  69,  19)),
    dict(name="VODKA",   emoji="🍸", symbol="V", mult_add=0.30,
         blur=0, wobble=0, speed=0, delay=1, color=(160, 216, 239)),
]
MAX_DRINKS = 10

# ─────────────────────────────────────────────────────────────────────────────
#  OBSTACLE CATALOGUE
#  Defines the four obstacle types that can appear on the track.
#
#  Fields:
#    label      — identifier string used in draw dispatch and collision checks
#    color/alt  — primary and secondary RGB colours for drawing
#    rel_w      — width as a fraction of the current lane pixel width
#                 (so obstacles scale correctly with perspective)
#    rel_h      — height as a fraction of lane pixel width (same reason)
#    block_jump — True means the obstacle is too tall to jump over;
#                 these are drawn with a red X to signal "impossible".
#                 The player must avoid them by switching lanes.
# ─────────────────────────────────────────────────────────────────────────────
OBS_TYPES = [
    dict(label="FENCE",   color=(200, 168, 75), alt=(139, 105, 20),
         rel_w=0.90, rel_h=0.55, block_jump=False),
    dict(label="HAY",     color=(232, 192, 96), alt=(160, 120, 48),
         rel_w=0.95, rel_h=0.50, block_jump=False),
    dict(label="WALL",    color=(140,  70, 50), alt=(100,  42, 28),
         rel_w=1.00, rel_h=0.95, block_jump=True),
    dict(label="HURDLE",  color=(93,  173, 226), alt=(41, 128, 185),
         rel_w=0.85, rel_h=0.60, block_jump=False),
]

# ─────────────────────────────────────────────────────────────────────────────
#  PERSPECTIVE HELPERS
#  The track uses a simple linear perspective model.
#
#  "depth" is a float in [0.0, 1.0]:
#    1.0  = on the horizon (far away, tiny)
#    0.0  = right at the player's feet (full size, bottom of screen)
#
#  All objects (obstacles, guards, track markings) carry a depth value that
#  decreases each frame as the horse gallops forward. The helper functions
#  below convert depth → screen coordinates and pixel sizes.
# ─────────────────────────────────────────────────────────────────────────────
def depth_to_y(depth: float) -> float:
    """Convert a depth value to a screen Y pixel position.
    depth=1.0 maps to HORIZON_Y (top of track), depth=0.0 maps to GROUND_Y."""
    return HORIZON_Y + (GROUND_Y - HORIZON_Y) * (1.0 - depth)

def depth_to_scale(depth: float) -> float:
    """Return a linear scale factor for an object at this depth.
    1.0 at depth=0 (full size at feet), 0.0 at depth=1 (invisible at horizon)."""
    return max(0.0, 1.0 - depth)

def lane_to_x(lane: int, depth: float) -> float:
    """Return the screen X pixel for the centre of a lane at a given depth.
    At depth=0 the lanes are at their full-width LANE_FEET_X positions.
    At depth=1 (horizon) all lanes converge to the screen centre (W/2)."""
    t = 1.0 - depth  # 0 at horizon, 1 at feet — drives the perspective taper
    cx = W / 2       # all lanes vanish to the centre of the screen
    foot_x = LANE_FEET_X[lane]
    return cx + (foot_x - cx) * t

def lane_pixel_width(depth: float) -> float:
    """Return how many pixels wide one lane appears at this depth.
    Used to size obstacles, wall panels, kerb segments, etc. so they
    automatically shrink as they recede toward the horizon."""
    t = 1.0 - depth
    full_span = LANE_FEET_X[2] - LANE_FEET_X[0]  # total track width in px at player position
    return (full_span / LANE_COUNT) * t

# ─────────────────────────────────────────────────────────────────────────────
#  UTILITY
# ─────────────────────────────────────────────────────────────────────────────
def draw_round_rect(surface, color, rect, radius=8, border=0, border_color=None):
    """Convenience wrapper: fill a rounded rect, then optionally draw a border.
    Used for UI panels, drink cards, and the scoreboard box."""
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surface, border_color, rect, border, border_radius=radius)

# ─────────────────────────────────────────────────────────────────────────────
#  OBSTACLE CLASS
#  Represents a single obstacle on the track (fence, hay bale, wall, hurdle).
#  Each obstacle has a lane (0–2), a depth (starts near 1.0 at spawn, counts
#  down to 0 as it approaches the player), and visual/collision properties
#  copied from the OBS_TYPES catalogue.
#
#  Key design note — perspective rendering:
#    The on-screen size and position are derived entirely from self.depth using
#    the lane_to_x / lane_pixel_width helpers. There are no fixed pixel sizes
#    stored; everything scales automatically as depth changes each frame.
# ─────────────────────────────────────────────────────────────────────────────
class Obstacle:
    def __init__(self, lane: int, otype: dict, spawn_depth: float = 1.0):
        # Copy all properties from the OBS_TYPES catalogue entry
        self.lane       = lane          # which of the 3 lanes (0=left, 1=centre, 2=right)
        self.depth      = spawn_depth   # current perspective depth; decreases each frame
        self.label      = otype["label"]
        self.color      = otype["color"]
        self.alt        = otype["alt"]
        self.rel_w      = otype["rel_w"]   # width fraction of lane pixel width
        self.rel_h      = otype["rel_h"]   # height fraction of lane pixel width
        self.block_jump = otype["block_jump"]  # True = cannot be jumped (WALL type)
        self.is_ghost   = False   # True for the one passable lane in a triple-fence wave

    def update(self, speed: float):
        """Advance the obstacle one frame toward the player by subtracting
        game_speed from depth. When depth reaches 0 the obstacle has passed."""
        self.depth -= speed

    def screen_rect(self) -> pygame.Rect:
        """Calculate the bounding pygame.Rect for this obstacle in screen pixels.
        Width and height scale with depth so the obstacle looks correct in
        perspective. Called every frame (no caching needed — depth changes each frame)."""
        cx   = lane_to_x(self.lane, self.depth)
        base = depth_to_y(self.depth)
        lw   = lane_pixel_width(self.depth)
        w    = lw * self.rel_w
        h    = lw * self.rel_h
        return pygame.Rect(cx - w / 2, base - h, w, h)

    def draw(self, surf: pygame.Surface, drunk_level: int = 0):
        """Main draw entry point. Decides whether to draw the obstacle as a
        ghost (semi-transparent, used for the one passable lane in a triple-fence
        wave) or normally. Also draws the perspective shadow before the body.

        drunk_level is passed in so the ghost transparency can increase when the
        player is drunk — making it harder to distinguish the safe lane."""
        r = self.screen_rect()
        if r.width < 2 or r.height < 2:  # skip if too small to see (deep in distance)
            return
        is_ghost = getattr(self, "is_ghost", False)

        # ── Perspective shadow — stretches toward player as depth → 0 ────────
        # As depth decreases (obstacle gets closer) the shadow trapezoid grows
        # taller, simulating a long shadow cast toward the viewer.
        if not is_ghost:
            shadow_reach = int(r.height * (1.5 + (1.0 - self.depth) * 6))
            shadow_alpha = max(0, min(120, int(90 * (1.0 - self.depth * 0.8))))
            sh = pygame.Surface((r.width + shadow_reach, shadow_reach + 4), pygame.SRCALPHA)
            pts = [
                (shadow_reach // 2,          0),
                (shadow_reach // 2 + r.width, 0),
                (shadow_reach + r.width,      shadow_reach + 4),
                (0,                           shadow_reach + 4),
            ]
            pygame.draw.polygon(sh, (0, 0, 0, shadow_alpha), pts)
            surf.blit(sh, (r.x - shadow_reach // 2, r.bottom - 4))

        if is_ghost:
            ghost_alpha = min(220, 80 + drunk_level * 14)
            tmp = pygame.Surface((r.width + 20, r.height + 20), pygame.SRCALPHA)
            tmp.fill((0, 0, 0, 0))
            r_local = pygame.Rect(10, 10, r.width, r.height)
            if self.label == "FENCE":
                self._draw_fence_on(tmp, r_local)
            tmp.set_alpha(ghost_alpha)
            surf.blit(tmp, (r.x - 10, r.y - 10))
        else:
            if self.label == "FENCE":
                self._draw_fence(surf, r)
            elif self.label == "HAY":
                self._draw_hay(surf, r)
            elif self.label == "WALL":
                self._draw_wall(surf, r)
            elif self.label == "HURDLE":
                self._draw_hurdle(surf, r)

    def _draw_fence(self, surf, r):
        """Draw a wooden fence: 5 vertical posts + 2 horizontal rails,
        with a drop shadow and highlight stripe on each element."""
        # Drop shadow
        sh = pygame.Surface((r.width + 8, r.height + 8), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 100), (0, 0, r.width + 8, r.height + 8), border_radius=3)
        surf.blit(sh, (r.x - 2, r.y + 5))
        # Posts
        post_w  = max(3, r.width // 6)
        post_hi = tuple(min(255, c + 50) for c in self.alt)
        for i in range(5):
            px = r.x + i * r.width // 4
            pygame.draw.rect(surf, self.alt,  (px, r.y, post_w, r.height), border_radius=2)
            pygame.draw.rect(surf, post_hi,   (px, r.y, max(1, post_w // 3), r.height))
        # Horizontal rails with highlight
        rail_h  = max(3, r.height // 4)
        rail_hi = tuple(min(255, c + 60) for c in self.color)
        for frac in (0.18, 0.58):
            ry = r.y + int(r.height * frac)
            pygame.draw.rect(surf, self.color, (r.x, ry, r.width, rail_h), border_radius=2)
            pygame.draw.rect(surf, rail_hi,   (r.x, ry, r.width, max(1, rail_h // 3)))
        pygame.draw.rect(surf, (0, 0, 0), r, 1)

    def _draw_fence_on(self, surf, r):
        """Same visual as _draw_fence but draws onto an arbitrary surface.
        Used when rendering the ghost (semi-transparent) version of a fence —
        we draw onto a temp SRCALPHA surface then blit it at reduced opacity."""
        post_w  = max(3, r.width // 6)
        post_hi = tuple(min(255, c + 50) for c in self.alt)
        for i in range(5):
            px = r.x + i * r.width // 4
            pygame.draw.rect(surf, self.alt,  (px, r.y, post_w, r.height), border_radius=2)
            pygame.draw.rect(surf, post_hi,   (px, r.y, max(1, post_w // 3), r.height))
        rail_h  = max(3, r.height // 4)
        rail_hi = tuple(min(255, c + 60) for c in self.color)
        for frac in (0.18, 0.58):
            ry = r.y + int(r.height * frac)
            pygame.draw.rect(surf, self.color, (r.x, ry, r.width, rail_h), border_radius=2)
            pygame.draw.rect(surf, rail_hi,   (r.x, ry, r.width, max(1, rail_h // 3)))
        pygame.draw.rect(surf, (0, 0, 0), r, 1)

    def _draw_hay(self, surf, r):
        """Draw a hay bale: a rounded rectangle with horizontal straw stripes
        and a bright top highlight to suggest a lit surface."""
        # Elliptical drop shadow beneath the bale
        sh = pygame.Surface((r.width + 8, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 100), (0, 0, r.width + 8, 10))
        surf.blit(sh, (r.x - 4, r.bottom + 1))
        # Main bale body with rounded corners
        pygame.draw.rect(surf, self.color, r, border_radius=5)
        # Straw stripes
        stripe_h = max(1, r.height // 7)
        dark     = tuple(max(0, c - 40) for c in self.alt)
        for i in range(1, 6):
            sy = r.y + i * r.height // 6
            pygame.draw.rect(surf, self.alt, (r.x + 2, sy, r.width - 4, stripe_h))
        # Top highlight sheen
        hi_col = tuple(min(255, c + 70) for c in self.color)
        pygame.draw.rect(surf, hi_col, (r.x + 3, r.y + 3, r.width - 6, max(2, r.height // 6)), border_radius=3)
        pygame.draw.rect(surf, (0, 0, 0), r, 1, border_radius=5)

    def _draw_wall(self, surf, r):
        """Tall impassable wall — block_jump=True. Drawn with brick texture + red X."""
        # Shadow
        sh = pygame.Surface((r.width + 8, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 120), (0, 0, r.width + 8, 10))
        surf.blit(sh, (r.x - 4, r.bottom + 1))
        # Brick base colour
        pygame.draw.rect(surf, self.color, r, border_radius=2)
        # Brick rows
        bh = max(4, r.height // 6)
        for row in range(r.height // bh + 1):
            by = r.y + row * bh
            offset = (row % 2) * (r.width // 4)
            bw = max(6, r.width // 3)
            dark = tuple(max(0, c - 30) for c in self.color)
            for col in range(-1, 5):
                bx = r.x + col * bw + offset
                bx = max(r.x, min(bx, r.right - 2))
                pygame.draw.rect(surf, dark,
                    (bx, max(r.y, by), min(2, r.right - bx), min(bh, r.bottom - by)))
            pygame.draw.line(surf, tuple(max(0, c - 20) for c in self.color),
                             (r.x, by), (r.right, by), 1)
        # Highlight top edge
        hi = tuple(min(255, c + 50) for c in self.color)
        pygame.draw.rect(surf, hi, (r.x, r.y, r.width, max(2, r.height // 8)), border_radius=2)
        pygame.draw.rect(surf, (0, 0, 0), r, 2, border_radius=2)
        # Big red X — "cannot jump this"
        if r.width > 8 and r.height > 8:
            pad = max(4, min(r.width, r.height) // 6)
            x1, y1, x2, y2 = r.x + pad, r.y + pad, r.right - pad, r.bottom - pad
            pygame.draw.line(surf, (220, 40, 40), (x1, y1), (x2, y2), max(3, r.width // 8))
            pygame.draw.line(surf, (220, 40, 40), (x2, y1), (x1, y2), max(3, r.width // 8))
            # White border on X for readability
            pygame.draw.line(surf, (255, 200, 200), (x1, y1), (x2, y2), max(1, r.width // 16))
            pygame.draw.line(surf, (255, 200, 200), (x2, y1), (x1, y2), max(1, r.width // 16))

    def _draw_hurdle(self, surf, r):
        """Draw a hurdle: two vertical posts with two horizontal cross-bars.
        Highlights on the top edge of each bar improve readability at speed."""
        # Drop shadow
        sh = pygame.Surface((r.width + 8, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 100), (0, 0, r.width + 8, 10))
        surf.blit(sh, (r.x - 4, r.bottom + 1))
        post_w = max(4, r.width // 8)
        bar_h  = max(4, r.height // 5)
        post_hi = tuple(min(255, c + 60) for c in self.alt)
        bar_hi  = tuple(min(255, c + 60) for c in self.color)
        # Vertical posts (with highlight)
        for px in (r.x, r.right - post_w):
            pygame.draw.rect(surf, self.alt,  (px, r.y, post_w, r.height), border_radius=2)
            pygame.draw.rect(surf, post_hi,   (px, r.y, max(1, post_w // 3), r.height))
        # Cross bar (bold, with top highlight)
        bar_y = r.y + r.height // 3
        pygame.draw.rect(surf, self.color, (r.x, bar_y, r.width, bar_h), border_radius=2)
        pygame.draw.rect(surf, bar_hi,    (r.x, bar_y, r.width, max(1, bar_h // 3)))
        # Lower thin bar
        bar2_y = r.y + int(r.height * 0.72)
        pygame.draw.rect(surf, self.color, (r.x + post_w, bar2_y, r.width - post_w * 2, max(2, bar_h // 2)), border_radius=2)
        pygame.draw.rect(surf, (0, 0, 0), r, 1)


# ─────────────────────────────────────────────────────────────────────────────
#  GUARD CLASS  (enemy)
#  Security guards walk down the track toward the player and home in on the
#  player's lane. Touching a guard ends the race, same as hitting an obstacle.
#
#  AI behaviour:
#    The guard starts in a random lane and switches to the player's lane
#    once, at a random point between depth 0.90 and 0.76 (roughly 2 seconds
#    before contact). This gives the player a narrow warning window to dodge.
#    The guard never switches more than once, preventing a frustrating "follow"
#    behaviour.
# ─────────────────────────────────────────────────────────────────────────────
class Guard:
    def __init__(self, lane: int):
        self.lane         = lane    # current lane (0–2)
        self.depth        = 1.0    # starts at the horizon
        self.anim         = 0      # frame counter driving the walk-cycle animation
        self.has_switched = False  # AI flag: guard moves to player lane only once

    def update(self, speed: float, player_lane: int):
        """Advance the guard toward the player and handle lane-switching AI.
        Guards move at 70% of game_speed so they're slower than obstacles —
        giving the player a slightly longer window to react."""
        self.depth -= speed * 0.70  # guards are slower than obstacles
        self.anim  += 1             # increment walk-cycle counter
        # Switch to the player's lane roughly 2 seconds before contact.
        # Guard moves at speed*0.70; contact zone is depth≈0.07.
        # So "2 seconds away" ≈ depth 0.74–0.90. A random roll in that window
        # prevents the switch always happening at the same moment.
        # Hard deadline at depth 0.76 guarantees the switch always happens
        # before the guard reaches the player, preventing impossible situations.
        if not self.has_switched:
            if self.depth < 0.90 and random.random() < 0.030:
                self.lane         = player_lane
                self.has_switched = True
            elif self.depth <= 0.76:
                self.lane         = player_lane
                self.has_switched = True

    def draw(self, surf: pygame.Surface):
        """Draw the guard as a hi-vis-vest security officer. All sizes scale with
        depth so the figure looks correct in perspective. Very distant guards
        (scale < 0.04) are skipped entirely — they'd be invisible anyway."""
        cx   = lane_to_x(self.lane, self.depth)  # screen X centre
        base = depth_to_y(self.depth)             # screen Y ground position
        sc   = depth_to_scale(self.depth)         # linear size scale factor
        if sc < 0.04:  # too small/far to be worth drawing
            return
        lw  = lane_pixel_width(self.depth)
        bw  = max(5, int(lw * 0.38))
        bh  = max(8, int(lw * 0.85))
        bx  = int(cx - bw / 2)
        by  = int(base - bh)

        # Ground shadow
        if sc > 0.15:
            sh = pygame.Surface((bw + 12, 10), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 80), (0, 0, bw + 12, 10))
            surf.blit(sh, (bx - 6, int(base) - 3))

        # Legs with walk animation
        walk = int(math.sin(self.anim * 0.28) * bw * 0.35)
        leg_h = max(3, bh // 4)
        lleg_col = (22, 22, 38)
        pygame.draw.rect(surf, lleg_col, (bx + bw // 4 - bw // 6 + walk,  by + bh, max(2, bw // 4), leg_h), border_radius=2)
        pygame.draw.rect(surf, lleg_col, (bx + bw // 2 + bw // 6 - walk,  by + bh, max(2, bw // 4), leg_h), border_radius=2)
        # Boots
        if sc > 0.3:
            pygame.draw.ellipse(surf, (20, 15, 10),
                                (bx + bw // 4 - bw // 6 + walk - 1, by + bh + leg_h - 2, max(4, bw // 3), max(3, leg_h // 2)))
            pygame.draw.ellipse(surf, (20, 15, 10),
                                (bx + bw // 2 + bw // 6 - walk - 1, by + bh + leg_h - 2, max(4, bw // 3), max(3, leg_h // 2)))

        # Body — dark uniform
        pygame.draw.rect(surf, (22, 22, 38), (bx, by, bw, bh), border_radius=max(2, bw // 6))

        # Hi-vis vest (bright yellow-green)
        vest_y = by + bh // 5
        vest_h = max(3, bh * 2 // 5)
        pygame.draw.rect(surf, (50, 210, 60), (bx + 1, vest_y, bw - 2, vest_h), border_radius=2)
        # Vest highlight
        if sc > 0.2:
            pygame.draw.rect(surf, (120, 240, 120), (bx + 2, vest_y + 1, max(1, bw // 3), max(1, vest_h // 3)))
        # SECURITY text on vest
        if sc > 0.45 and bw > 22:
            fsize = max(7, bw // 4)
            fnt   = pygame.font.SysFont("monospace", fsize, bold=True)
            txt   = fnt.render("SEC", True, (10, 60, 10))
            surf.blit(txt, txt.get_rect(center=(int(cx), vest_y + vest_h // 2)))

        # Arms spread wide (blocking)
        arm_y   = by + bh // 3
        arm_len = max(5, int(bw * 1.2))
        arm_w   = max(2, bw // 5)
        pygame.draw.line(surf, (22, 22, 38), (bx, arm_y), (bx - arm_len, arm_y + arm_len // 3), arm_w)
        pygame.draw.line(surf, (22, 22, 38), (bx + bw, arm_y), (bx + bw + arm_len, arm_y + arm_len // 3), arm_w)
        # Gloves
        if sc > 0.2:
            pygame.draw.circle(surf, (50, 210, 60), (bx - arm_len, arm_y + arm_len // 3), max(2, arm_w))
            pygame.draw.circle(surf, (50, 210, 60), (bx + bw + arm_len, arm_y + arm_len // 3), max(2, arm_w))

        # Head
        head_r = max(4, bw // 2)
        pygame.draw.circle(surf, (210, 168, 120), (int(cx), by - head_r // 2), head_r)
        # Cap
        cap_col = (22, 22, 38)
        pygame.draw.ellipse(surf, cap_col,
                            (int(cx) - head_r, by - head_r * 2 + head_r // 2, head_r * 2, head_r))
        pygame.draw.rect(surf, cap_col,
                         (int(cx) - head_r - 2, by - head_r // 2 + 1, head_r * 2 + 4, max(2, head_r // 3)),
                         border_radius=1)
        # Eyes (white dots)
        if sc > 0.35 and head_r > 6:
            pygame.draw.circle(surf, (240, 240, 240), (int(cx) - head_r // 3, by - head_r // 2), max(1, head_r // 4))
            pygame.draw.circle(surf, (240, 240, 240), (int(cx) + head_r // 3, by - head_r // 2), max(1, head_r // 4))


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN GAME CLASS
#  DerbyDash is a single class that owns all game state and runs the main loop.
#
#  Responsibility breakdown by method group:
#    __init__          — pygame setup, font loading, cutscene image loading
#    _reset_bar        — reset drink selection state (called on new game)
#    _reset_race       — reset all race variables (called just before race starts)
#    run               — the main loop: tick clock, dispatch to update+draw
#    _handle_events    — process the pygame event queue each frame
#    _bar_keydown      — respond to key presses in the bar phase
#    _add/_remove_drink— modify the drink order and recompute multiplier/effects
#    _start_race       — transition bar → cutscene (or → race if no images)
#    _update_bar       — per-frame bar logic (currently a no-op)
#    _draw_bar*        — render the bar scene and all its sub-elements
#    _race_keydown     — queue player input with vodka delay applied
#    _process_input_queue — fire queued inputs when their delay timer expires
#    _spawn_wave       — generate a new obstacle/guard wave (always survivable)
#    _update_race      — advance all race state: physics, particles, AI, collision
#    _draw_race        — compose the race frame: background → objects → player → HUD
#    _draw_track_bg    — draw the 12-layer stadium + track background
#    _draw_player      — draw the front-facing horse + jockey
#    _draw_hud         — draw score, multiplier, effect pills, control hints
#    _cutscene_*       — fade-in/hold/fade-out cutscene images between bar and race
#    _record_score     — save final score to the in-memory leaderboard
#    _draw_gameover    — render the game-over panel with score breakdown
# ─────────────────────────────────────────────────────────────────────────────
class DerbyDash:
    # ── Game states ───────────────────────────────────────────────────────────
    # The game is always in one of these four states, which controls which
    # update/draw pair is called each frame in the main loop.
    STATE_BAR       = "bar"       # player is at the bar choosing drinks
    STATE_RACE      = "race"      # the race is running
    STATE_GAMEOVER  = "gameover"  # player crashed/caught; showing score
    STATE_CUTSCENE  = "cutscene"  # playing the narrative images between bar and race

    def __init__(self):
        """Initialise pygame, create the window, load fonts, and attempt to load
        cutscene images from the same folder as the script. Fonts are pre-created
        here so they are not recreated every frame (which would be slow)."""
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption(TITLE)
        self.clock  = pygame.time.Clock()

        # Five font sizes used across the UI — all monospace for a retro look.
        # f_huge: game-over title   f_large: score/HUD   f_med: labels
        # f_small: body text        f_tiny: fine detail/tooltips
        self.f_huge   = pygame.font.SysFont("monospace", 64, bold=True)
        self.f_large  = pygame.font.SysFont("monospace", 32, bold=True)
        self.f_med    = pygame.font.SysFont("monospace", 18, bold=True)
        self.f_small  = pygame.font.SysFont("monospace", 13)
        self.f_tiny   = pygame.font.SysFont("monospace", 11)

        # ── Cutscene images ───────────────────────────────────────────────────
        # Three PNG images (cutscene_1/2/3.png) live alongside the script.
        # They are scaled to fill the window and shown sequentially with a
        # fade-in → hold → fade-out transition. Missing images are silently
        # skipped — the game jumps straight to the race if none are found.
        _here = os.path.dirname(os.path.abspath(__file__))
        self._cutscene_images = []
        for _img_name in ["cutscene_1.png", "cutscene_2.png", "cutscene_3.png"]:
            _img_path = os.path.join(_here, _img_name)
            try:
                img = pygame.image.load(_img_path).convert()
                img = pygame.transform.smoothscale(img, (W, H))
                self._cutscene_images.append(img)
            except Exception:
                pass  # silently skip missing images
        self._cutscene_idx   = 0    # which image we're on
        self._cutscene_alpha = 0    # fade-in alpha (0→255)
        self._cutscene_fade  = "in" # "in" | "hold" | "out"
        self._cutscene_timer = 0
        self.high_scores   = []   # list of (score, survive_time, drunk_level)
        self.last_score    = None
        self._reset_bar()
        self.state = self.STATE_BAR

    # ── Reset helpers ─────────────────────────────────────────────────────────
    def _reset_bar(self):
        """Reset everything that belongs to the bar/drink-selection phase.
        Called at the start of every new game (including restarts from game-over).
        The fx_ counters persist into the race, so they must be zeroed here."""
        self.drink_history  = []    # ordered list of drinks chosen (used for multiplier sum)
        self.multiplier     = 1.0  # score multiplier — starts at ×1.0 (no drinks)
        self.selected_drink = 0    # index into DRINKS for the currently highlighted card
        self.fx_blur   = 0   # total beer stacks; drives vision-blur intensity
        self.fx_wobble = 0   # total cider stacks; drives screen sway & stumble
        self.fx_speed  = 0   # total whiskey stacks; added to game_speed each frame
        self.fx_delay  = 0   # total vodka stacks; added to input queue delay in frames
        self.drunk_level = 0 # sum of all fx_ values; shorthand for spawn distance / triple-fence

    def _reset_race(self):
        """Reset everything that belongs to the race phase.
        Called just before the cutscene starts (or directly before the race if
        there are no cutscene images). The fx_ drink effect counters are NOT
        reset here — they are set in _reset_bar and intentionally persist."""
        # Active objects on the track
        self.obstacles     = []    # list of Obstacle instances currently on track
        self.guards        = []    # list of Guard instances currently on track

        # Player state
        self.player_lane   = 1     # start in the centre lane
        self.player_y      = 0.0   # vertical pixel offset from ground; negative = in air
        self.is_jumping    = False
        self.jump_vel      = 0.0   # current vertical velocity (positive = falling)

        # Score / time
        self.base_score    = 0     # survive_time * 10, before multiplier
        self.survive_time  = 0.0   # seconds elapsed since race start
        self.race_frame    = 0     # integer frame counter (used for timing and animation)

        # Speed and spawning
        self.game_speed    = 0.010  # depth units subtracted from each object per frame
        self.spawn_timer   = 0      # counts frames since last wave spawned
        self.spawn_interval = 80    # frames between waves (shrinks over time)
        self.bg_offset     = 0.0    # scrolling offset used by track markings and stickers

        # Drunk visual effect state
        self.input_queue   = []     # list of (frame_to_fire, action) — vodka delay buffer
        self.sway_angle    = 0.0    # current camera rotation angle (cider wobble)
        self.distort_phase = 0.0    # phase counter for the wobble sine wave
        self.stumble_timer = 0      # frames until next random stumble event
        self.stumble_dx    = 0.0    # current horizontal stumble offset in pixels
        self.drunk_flash   = 0      # countdown frames for the flash overlay on heavy drinking

        # Particle system
        self.particles     = []     # list of particle dicts: x,y,vx,vy,life,max_life,r,color
        self._was_jumping  = False  # True last frame; used to detect the moment of landing

        # NOTE: fx_blur, fx_wobble, fx_speed, fx_delay, drunk_level are set in
        # _reset_bar and deliberately NOT cleared here — they carry the player's
        # chosen drinks from the bar phase into the race.

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        """The game's main loop. Runs until the window is closed.
        Each iteration: cap frame rate → process events → update+draw the
        current state → flip the display buffer to the screen."""
        while True:
            dt = self.clock.tick(FPS)   # block until the next frame slot; dt = ms elapsed
            self._handle_events()       # process keyboard/mouse/quit events

            # Dispatch to the correct update+draw pair for the active state.
            # game-over has no update — it's a static screen waiting for input.
            if self.state == self.STATE_BAR:
                self._update_bar()
                self._draw_bar()
            elif self.state == self.STATE_CUTSCENE:
                self._update_cutscene()
                self._draw_cutscene()
            elif self.state == self.STATE_RACE:
                self._update_race()
                self._draw_race()
            elif self.state == self.STATE_GAMEOVER:
                self._draw_gameover()
            pygame.display.flip()   # swap back buffer → screen

    # ─────────────────────────────────────────────────────────────────────────
    #  EVENT HANDLING
    # ─────────────────────────────────────────────────────────────────────────
    def _handle_events(self):
        """Process all pending pygame events. Routes keyboard events to the
        appropriate handler for the current state. Mouse clicks advance
        cutscenes. QUIT (window close) exits immediately."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN:
                if self.state == self.STATE_BAR:
                    self._bar_keydown(event.key)
                elif self.state == self.STATE_CUTSCENE:
                    self._cutscene_advance()
                elif self.state == self.STATE_RACE:
                    self._race_keydown(event.key)
                elif self.state == self.STATE_GAMEOVER:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_r):
                        self._reset_bar()
                        self.state = self.STATE_BAR

            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.state == self.STATE_CUTSCENE:
                    self._cutscene_advance()
            if event.type == pygame.KEYUP:
                pass  # no keyup actions currently needed

    # ─────────────────────────────────────────────────────────────────────────
    #  BAR PHASE
    # ─────────────────────────────────────────────────────────────────────────
    def _bar_keydown(self, key):
        """Handle key presses in the bar state.
        LEFT/RIGHT browse drinks. ENTER/SPACE adds one. BACKSPACE removes last.
        R starts the race (allowed even with zero drinks — multiplier stays ×1)."""
        if key == pygame.K_LEFT:
            self.selected_drink = (self.selected_drink - 1) % len(DRINKS)
        elif key == pygame.K_RIGHT:
            self.selected_drink = (self.selected_drink + 1) % len(DRINKS)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._add_drink()
        elif key == pygame.K_BACKSPACE:
            self._remove_drink()
        elif key == pygame.K_r:
            self._start_race()

    def _add_drink(self):
        """Add the currently selected drink to the order (up to MAX_DRINKS).
        The multiplier is recalculated as 1.0 + sum of all mult_add values,
        and the relevant effect counter (fx_blur etc.) is incremented."""
        if len(self.drink_history) >= MAX_DRINKS:
            return  # silently ignore if the order is full
        d = DRINKS[self.selected_drink]
        self.drink_history.append(d)
        self.fx_blur   += d["blur"]
        self.fx_wobble += d["wobble"]
        self.fx_speed  += d["speed"]
        self.fx_delay  += d["delay"]
        self.drunk_level = self.fx_blur + self.fx_wobble + self.fx_speed + self.fx_delay
        self.multiplier  = 1.0 + sum(x["mult_add"] for x in self.drink_history)

    def _remove_drink(self):
        """Remove the most recently added drink (like a backspace).
        Recalculates multiplier and decrements the matching effect counter."""
        if not self.drink_history:
            return  # nothing to remove
        d = self.drink_history.pop()
        self.fx_blur   = max(0, self.fx_blur   - d["blur"])
        self.fx_wobble = max(0, self.fx_wobble - d["wobble"])
        self.fx_speed  = max(0, self.fx_speed  - d["speed"])
        self.fx_delay  = max(0, self.fx_delay  - d["delay"])
        self.drunk_level = self.fx_blur + self.fx_wobble + self.fx_speed + self.fx_delay
        self.multiplier  = 1.0 + sum(x["mult_add"] for x in self.drink_history)

    def _start_race(self):
        """Transition from the bar to the race. Resets all race variables, then
        either plays the cutscene (if images were loaded) or jumps straight to
        the race if no cutscene images are available."""
        self._reset_race()
        if self._cutscene_images:
            self._cutscene_idx   = 0
            self._cutscene_alpha = 0
            self._cutscene_fade  = "in"
            self._cutscene_timer = 0
            self.state = self.STATE_CUTSCENE
        else:
            self.state = self.STATE_RACE

    def _update_bar(self):
        """Per-frame update for the bar state. Currently a no-op — all bar
        logic is event-driven. Kept as a method for symmetry with other states
        in case animated elements need updating here in the future."""
        pass

    def _draw_bar_patrons(self, surf, counter_y, t):
        """Draw 4 pub patrons STANDING on bar stool footrests, leaning on counter.
        The footrest ring is ~60px below the counter. Patrons stand on it with
        bent knees, feet on the ring, torso upright leaning forward onto the bar.
        This matches barman scale (~95px torso, head r=20)."""
        seats = [
            {"x": 90,      "facing":  1, "shirt": (155,  38,  38), "hair": (32, 18, 6),  "skin": (205,160,112), "glass_col": (240,190, 50,165)},
            {"x": 210,     "facing":  1, "shirt": ( 38,  88, 158), "hair": (20, 12, 4),  "skin": (218,172,125), "glass_col": (180,220,255,155)},
            {"x": W - 210, "facing": -1, "shirt": ( 48, 138,  58), "hair": (62, 42, 18), "skin": (198,148, 98), "glass_col": (240,190, 50,165)},
            {"x": W - 90,  "facing": -1, "shirt": (128,  58, 128), "hair": (22, 14, 4),  "skin": (210,165,118), "glass_col": (180,220,255,155)},
        ]

        # The stool footrest ring sits this many px below the counter top
        FOOTREST_OFFSET = 62

        for i, p in enumerate(seats):
            px2        = p["x"]
            phase      = i * math.pi * 0.5
            sway       = int(math.sin(t * 0.52 + phase) * 2)
            nod        = int(math.sin(t * 0.36 + phase) * 2)
            tor_x      = px2 + sway

            # Key y-positions — patron SITS on stool seat, feet on footrest
            seat_y     = counter_y + 28              # patrons sit lower (pushed down)
            foot_y     = counter_y + FOOTREST_OFFSET + 28 # footrest ring (lowered)
            hip_y      = seat_y                      # hips rest on seat
            tor_bot    = hip_y - 2                   # base of torso
            tor_top    = tor_bot - 92 + sway         # top of torso

            # ── Legs: hip on seat → knee bend → foot on footrest ──────────────
            for side, lx_off in ((-1, -12), (1, 12)):
                hip_x   = tor_x + lx_off
                # Knee hangs below seat, bent forward
                knee_x  = hip_x + side * 6
                knee_y  = seat_y + 28
                # Foot rests on footrest ring
                foot_x  = px2 + lx_off * 0.7
                # Upper leg: hip → knee
                pygame.draw.line(surf, (28, 18, 6),
                                 (int(hip_x), hip_y), (int(knee_x), knee_y), 8)
                # Lower leg: knee → foot
                pygame.draw.line(surf, (28, 18, 6),
                                 (int(knee_x), knee_y), (int(foot_x), foot_y), 8)
                # Shoe on footrest
                pygame.draw.ellipse(surf, (16, 10, 3),
                                    (int(foot_x) - 10, foot_y - 3, 20, 9))

            # ── Torso — upright, leaning slightly toward counter ──────────────
            pygame.draw.rect(surf, p["shirt"],
                             (tor_x - 24, tor_top, 48, tor_bot - tor_top),
                             border_radius=6)
            # Shirt collar / lapel
            pygame.draw.polygon(surf, (225, 220, 210), [
                (tor_x - 8, tor_top),
                (tor_x,     tor_top + 20),
                (tor_x + 8, tor_top),
            ])

            # ── Arm reaching for drink on counter ─────────────────────────────
            arm_reach = int(math.sin(t * 0.26 + phase) * 8) + 18
            arm_x  = tor_x + p["facing"] * arm_reach
            arm_y  = tor_top + 30
            pygame.draw.line(surf, p["shirt"],
                             (tor_x + p["facing"] * 20, arm_y),
                             (arm_x, arm_y + 8), 10)
            pygame.draw.circle(surf, p["skin"], (arm_x, arm_y + 8), 6)

            # Glass in hand
            gx = arm_x + p["facing"] * 8
            gy = arm_y + 2
            gl = pygame.Surface((22, 30), pygame.SRCALPHA)
            pygame.draw.rect(gl, (195, 215, 235, 72), (1,  0, 20, 28), border_radius=3)
            pygame.draw.rect(gl, p["glass_col"],       (2,  8, 18, 18), border_radius=2)
            pygame.draw.rect(gl, (255,255,255, 115),   (3, 10,  5, 14))
            surf.blit(gl, (gx - 11, gy - 12))

            # ── Other arm resting elbow on counter ────────────────────────────
            rest_x = tor_x - p["facing"] * 20
            pygame.draw.line(surf, p["shirt"],
                             (tor_x - p["facing"] * 20, arm_y),
                             (rest_x, counter_y - 4), 10)

            # ── Head ──────────────────────────────────────────────────────────
            head_r = 20
            head_x = tor_x + sway // 2
            head_y = tor_top - head_r + 2 + nod
            pygame.draw.circle(surf, p["skin"], (head_x, head_y), head_r)
            pygame.draw.ellipse(surf, p["hair"],
                                (head_x - head_r, head_y - head_r,
                                 head_r * 2, head_r + 4))
            eye_side = p["facing"]
            pygame.draw.circle(surf, (40, 25, 8),
                               (head_x + eye_side * 6, head_y - 2), 3)
            pygame.draw.circle(surf, (230, 200, 150),
                               (head_x + eye_side * 7, head_y - 3), 1)
            pygame.draw.circle(surf, tuple(max(0, c - 16) for c in p["skin"]),
                               (head_x - eye_side * 18, head_y + 2), 5)
            pygame.draw.arc(surf, (160, 100, 70),
                            (head_x + eye_side * 2, head_y + 8, 10, 6),
                            0, math.pi, 2)

    def _draw_bar(self):
        surf = self.screen
        t    = pygame.time.get_ticks() / 1000.0
        max_drunk = 10

        # ── BACKGROUND — warm amber pub interior ──────────────────────────────
        for i in range(H):
            frac = i / H
            col  = (int(26 + frac * 12), int(12 + frac * 8), int(0 + frac * 3))
            pygame.draw.line(surf, col, (0, i), (W, i))
        # Wood panelling
        for row in range(0, H - 120, 28):
            pygame.draw.line(surf, (42, 20, 4), (0, row), (W, row), 1)
            pygame.draw.line(surf, (54, 28, 8), (0, row + 2), (W, row + 2), 1)

        # ── BACK WALL MIRROR ─────────────────────────────────────────────────
        mir_y = 25
        pygame.draw.rect(surf, (38, 52, 65), (70, mir_y, W - 140, 120))
        pygame.draw.rect(surf, (62, 88, 110), (70, mir_y, W - 140, 2))
        pygame.draw.rect(surf, (62, 88, 110), (70, mir_y + 118, W - 140, 2))
        pygame.draw.rect(surf, (62, 88, 110), (70, mir_y, 2, 120))
        pygame.draw.rect(surf, (62, 88, 110), (W - 72, mir_y, 2, 120))
        # Bar sign in mirror
        sign = self.f_large.render("THE  DERBY", True, C_GOLD)
        surf.blit(sign, sign.get_rect(center=(W // 2, mir_y + 32)))
        pygame.draw.line(surf, C_DARK_GOLD, (W//2 - 130, mir_y + 48), (W//2 + 130, mir_y + 48), 1)
        sub_sign = self.f_tiny.render("EST. 1887  —  FINE ALES & SPIRITS", True, (160, 130, 60))
        surf.blit(sub_sign, sub_sign.get_rect(center=(W // 2, mir_y + 62)))

        # ── BOTTLE SHELF ─────────────────────────────────────────────────────
        shelf_y = mir_y + 122
        pygame.draw.rect(surf, (65, 38, 8),  (0, shelf_y, W, 12))
        pygame.draw.rect(surf, (88, 52, 14), (0, shelf_y, W, 3))

        bottles = [
            (110, (175, 70, 15),  (215, 100, 35), 17, 48),
            (148, (28,  85, 30),  (48,  135, 48), 13, 44),
            (182, (155, 18, 18),  (195, 45,  45), 16, 52),
            (215, (20,  48, 155), (38,  76,  195),12, 46),
            (246, (155, 155, 25),(195, 195, 55),  14, 42),
            (276, (95,  25, 95), (135, 45,  135), 16, 48),
            (W-276,(28, 115, 75), (48,  155, 105),15, 44),
            (W-244,(175, 95, 18),(215, 125, 38),  13, 50),
            (W-210,(18,  76, 155),(38, 106, 195), 17, 46),
            (W-177,(155, 38, 38),(195, 65,  65),  12, 52),
            (W-145,(45,  135, 45),(65, 175, 65),  16, 48),
            (W-110,(135, 75, 18),(175, 105, 38),  14, 44),
        ]
        for (bx, bc, bhi, bw2, bh2) in bottles:
            pygame.draw.rect(surf, bc,  (bx-bw2//2, shelf_y-bh2, bw2, bh2), border_radius=3)
            pygame.draw.rect(surf, bhi, (bx-bw2//2, shelf_y-bh2, max(2,bw2//4), bh2), border_radius=3)
            pygame.draw.rect(surf, bc,  (bx-bw2//4, shelf_y-bh2-13, bw2//2, 13))
            pygame.draw.rect(surf, (175, 138, 78), (bx-bw2//4-1, shelf_y-bh2-15, bw2//2+2, 4))
            pygame.draw.rect(surf, tuple(min(255,c+50) for c in bc),
                             (bx-bw2//2, mir_y+6, bw2, max(3,bh2//4)), border_radius=2)

        # ── BAR COUNTER ──────────────────────────────────────────────────────
        counter_y = H - 195
        for i in range(24):
            cc = (max(0,105-i*3), max(0,62-i*2), 8)
            pygame.draw.rect(surf, cc, (0, counter_y+i, W, 1))
        pygame.draw.rect(surf, (125, 78, 14), (0, counter_y, W, 3))
        pygame.draw.rect(surf, (52, 28, 4), (0, counter_y+24, W, H-counter_y-24))
        for xi in range(0, W, 55):
            pygame.draw.line(surf, (62, 35, 8), (xi, counter_y+24), (xi+38, H), 1)

        # Stools — draw all 6 (4 patron stools + 2 centre gap stools)
        all_stool_x = [90, 210, W//2 - 130, W//2 + 130, W - 210, W - 90]
        for sx in all_stool_x:
            # Seat
            pygame.draw.ellipse(surf, (68, 38, 8),  (sx-30, counter_y-6, 60, 16))
            pygame.draw.ellipse(surf, (88, 52, 14), (sx-28, counter_y-8, 56, 12))
            # Central pole all the way to floor
            pygame.draw.line(surf, (78, 46, 10), (sx, counter_y+10), (sx, H - 6), 6)
            # Footrest ring
            footrest_y = counter_y + 62
            pygame.draw.line(surf, (78, 46, 10), (sx-22, footrest_y), (sx+22, footrest_y), 4)
            # Base spread at floor
            pygame.draw.line(surf, (78, 46, 10), (sx-26, H - 6), (sx+26, H - 6), 5)

        # Glasses on counter
        for gx, gcol in ((W//2-65, (240,195,55,170)), (W//2+65, (175,215,255,155))):
            gl = pygame.Surface((24, 32), pygame.SRCALPHA)
            pygame.draw.rect(gl, (195,215,235,75),  (1,  0, 22, 30), border_radius=3)
            pygame.draw.rect(gl, gcol,               (2,  7, 20, 20), border_radius=2)
            pygame.draw.rect(gl, (255,255,255,115),  (3, 9,  5,  16))
            surf.blit(gl, (gx-12, counter_y-26))

        # ── BAR PATRONS ──────────────────────────────────────────────────────
        self._draw_bar_patrons(surf, counter_y, t)

        # ── BARMAN ──────────────────────────────────────────────────────────
        bm_x = W // 2
        bm_ground = counter_y - 8

        # Body — white shirt + black vest
        pygame.draw.rect(surf, (228,222,212), (bm_x-28, bm_ground-105, 56, 95), border_radius=6)
        pygame.draw.rect(surf, (22, 18,  12), (bm_x-24, bm_ground-103, 48, 90), border_radius=4)
        # Shirt wings visible either side
        pygame.draw.polygon(surf, (228,222,212), [
            (bm_x-10, bm_ground-103),(bm_x, bm_ground-80),(bm_x+10, bm_ground-103)
        ])
        # Bow tie
        pygame.draw.polygon(surf, (175,28,28), [
            (bm_x-7, bm_ground-95),(bm_x, bm_ground-89),(bm_x+7, bm_ground-95),
            (bm_x, bm_ground-101)
        ])

        # Arms shaking a cocktail shaker — shaker positioned to the RIGHT of head
        shake_x = int(math.sin(t * 4.2) * 8)    # fast horizontal shake
        shake_y = int(math.sin(t * 4.2 * 1.3) * 4)
        # Shaker sits to the right of the barman's head, raised
        shaker_cx = bm_x + 36 + shake_x          # 36px right of centre — closer to body
        shaker_cy = bm_ground - 118 + shake_y     # just above head
        shaker_x  = shaker_cx - 10
        shaker_y  = shaker_cy - 20
        # Right arm reaches out toward shaker from body
        pygame.draw.line(surf, (228,222,212),
                         (bm_x + 24, bm_ground - 65),
                         (shaker_cx + 10, shaker_cy + 8), 11)
        # Left arm also extends (holds from other side / steadies)
        pygame.draw.line(surf, (228,222,212),
                         (bm_x - 10, bm_ground - 70),
                         (shaker_cx - 10, shaker_cy + 8), 9)
        # Shaker — silver cylinder
        pygame.draw.rect(surf, (195, 198, 205), (shaker_x, shaker_y, 20, 38), border_radius=4)
        pygame.draw.rect(surf, (215, 220, 228), (shaker_x + 2, shaker_y + 2, 6, 34))  # highlight
        pygame.draw.rect(surf, (175, 178, 185), (shaker_x, shaker_y, 20, 8), border_radius=4)  # cap
        # Drops flying off
        for di in range(3):
            drop_phase = t * 5.0 + di * 2.1
            drop_x = shaker_cx + int(math.sin(drop_phase) * 14)
            drop_y = shaker_y - 4 - int(abs(math.sin(drop_phase * 0.7)) * 12)
            if int(drop_phase) % 2 == 0:
                pygame.draw.circle(surf, (140, 200, 240), (drop_x, drop_y), 2)

        # Head
        pygame.draw.circle(surf, (208,165,118), (bm_x, bm_ground-124), 22)
        # Receding hair
        pygame.draw.ellipse(surf, (58,36,16), (bm_x-20, bm_ground-146, 40, 16))
        # Moustache
        pygame.draw.ellipse(surf, (58,36,16), (bm_x-13, bm_ground-114, 26, 8))
        # Eyes (blink occasionally)
        blink = (int(t * 2.8) % 22 != 0)
        for ex in (-9, 9):
            pygame.draw.circle(surf, (48, 28, 8), (bm_x+ex, bm_ground-126), 4)
            if blink:
                pygame.draw.circle(surf, (240,198,140), (bm_x+ex-1, bm_ground-127), 1)
        # Eyebrow raise (animated when speaking)
        br = int(abs(math.sin(t * 0.7)) * 3)
        for ex, slope in ((-12, 1), (12, -1)):
            pygame.draw.line(surf, (58,36,16),
                             (bm_x+ex, bm_ground-133-br),
                             (bm_x+ex+slope*8, bm_ground-135-br), 2)

        # ── SPEECH BUBBLE ────────────────────────────────────────────────────
        d_sel = DRINKS[self.selected_drink]
        barman_quips = {
            "WATER":   ["Water? At a derby?", "...alright then."],
            "BEER":    ["Classic choice mate.", "The ales are fresh!"],
            "CIDER":   ["Ooh, a cider fan!", "Good vintage that."],
            "WHISKEY": ["Single malt coming", "right up, sir."],
            "VODKA":   ["Vodka?! You sure", "you wanna race after?"],
        }
        blines = barman_quips.get(d_sel["name"], ["What'll it be?"])
        if self.drunk_level >= 8:
            blines = ["Mate... I think you've", "had quite enough now."]
        elif self.drunk_level >= 5:
            blines = ["You sure you're fit", "to ride like that?"]
        elif len(self.drink_history) == 0:
            blines = ["Welcome to The Derby!", "What can I get ya?"]

        bw2 = 210
        bh2 = 16 + len(blines) * 22
        bub_x = bm_x + 36
        bub_y = bm_ground - 185
        pygame.draw.rect(surf, (244,240,228), (bub_x, bub_y, bw2, bh2), border_radius=10)
        pygame.draw.rect(surf, (175,145,75),  (bub_x, bub_y, bw2, bh2), 2, border_radius=10)
        pygame.draw.polygon(surf, (244,240,228), [
            (bub_x+10, bub_y+bh2),
            (bub_x-14, bub_y+bh2+16),
            (bub_x+30, bub_y+bh2),
        ])
        for li, line in enumerate(blines):
            lt = self.f_small.render(line, True, (28,18,4))
            surf.blit(lt, (bub_x+10, bub_y+8+li*22))

        # ── DRINK MENU on counter ─────────────────────────────────────────────
        menu_label = self.f_med.render("WHAT'LL IT BE?", True, C_GOLD)
        surf.blit(menu_label, menu_label.get_rect(center=(W//2, counter_y - 12)))

        card_w, card_h = 124, 88
        gap  = 10
        total = len(DRINKS) * card_w + (len(DRINKS)-1) * gap
        sx   = W//2 - total//2

        for i, d2 in enumerate(DRINKS):
            cx  = sx + i * (card_w + gap)
            sel = (i == self.selected_drink)
            bg  = (48, 26, 4) if sel else (32, 16, 2)
            bd  = d2["color"] if sel else (75, 46, 8)
            draw_round_rect(surf, bg, (cx, counter_y-card_h, card_w, card_h), 7,
                            border=2 if sel else 1, border_color=bd)
            if sel:
                gl = pygame.Surface((card_w+16, card_h+16), pygame.SRCALPHA)
                pygame.draw.rect(gl, d2["color"]+(42,), (0,0,card_w+16,card_h+16), border_radius=11)
                surf.blit(gl, (cx-8, counter_y-card_h-8))
                draw_round_rect(surf, bg, (cx, counter_y-card_h, card_w, card_h), 7,
                                border=2, border_color=d2["color"])
            # Try to render emoji using a system font that supports them
            try:
                emoji_font = pygame.font.SysFont("segoeuiemoji,applesymbols,notocoloremoji", 32)
                sym = emoji_font.render(d2["emoji"], True, d2["color"])
            except Exception:
                sym = self.f_large.render(d2["symbol"], True, d2["color"])
            surf.blit(sym, sym.get_rect(center=(cx+card_w//2, counter_y-card_h+26)))
            nm2 = self.f_small.render(d2["name"],  True, d2["color"])
            surf.blit(nm2, nm2.get_rect(center=(cx+card_w//2, counter_y-card_h+50)))
            effects = []
            if d2["blur"]:   effects.append(f"+{d2['blur']}blur")
            if d2["wobble"]: effects.append(f"+{d2['wobble']}wobble")
            if d2["speed"]:  effects.append(f"+{d2['speed']}speed")
            if d2["delay"]:  effects.append(f"+{d2['delay']}delay")
            eff_str = "  ".join(effects) if effects else "no effect"
            bonus_str = f"+{d2['mult_add']:.2f}" if d2['mult_add'] > 0 else "no bonus"
            ms2 = self.f_tiny.render(f"{bonus_str}  {eff_str}", True, (175,138,58))
            surf.blit(ms2, ms2.get_rect(center=(cx+card_w//2, counter_y-card_h+68)))
            if sel:
                ar = self.f_tiny.render("SELECTED", True, d2["color"])
                surf.blit(ar, ar.get_rect(center=(cx+card_w//2, counter_y-card_h+82)))

        # ── ORDER HISTORY + DRUNK METER ───────────────────────────────────────
        hist_lbl = self.f_tiny.render(
            f"ORDERED: {len(self.drink_history)}/{MAX_DRINKS}    "
            f"MULT: x{self.multiplier:.2f}   blur:{self.fx_blur} wobble:{self.fx_wobble} speed:{self.fx_speed} delay:{self.fx_delay}",  # cumulative
            True, C_DARK_GOLD)
        surf.blit(hist_lbl, hist_lbl.get_rect(center=(W//2, counter_y+10)))
        mw, mh = 255, 7
        mx2 = W//2 - mw//2
        my2 = counter_y + 22
        pygame.draw.rect(surf, (22, 10, 2), (mx2, my2, mw, mh))
        frac = min(self.drunk_level / max_drunk, 1.0)
        mc2  = C_GREEN if frac < 0.4 else (C_GOLD if frac < 0.7 else C_RED)
        pygame.draw.rect(surf, mc2, (mx2, my2, int(mw * frac), mh))
        pygame.draw.rect(surf, C_DARK_GOLD, (mx2, my2, mw, mh), 1)
        sl = self.f_tiny.render("SOBER",   True, C_DARK_GOLD)
        wl = self.f_tiny.render("WRECKED", True, C_DARK_GOLD)
        surf.blit(sl, (mx2, my2+mh+2))
        surf.blit(wl, (mx2+mw-wl.get_width(), my2+mh+2))

        # ── SCOREBOARD — top right of bar ────────────────────────────────────
        sb_x, sb_y, sb_w = 12, 148, 200
        sb_h = min(8, max(1, len(self.high_scores))) * 20 + 52
        draw_round_rect(surf, (18, 8, 0), (sb_x, sb_y, sb_w, sb_h), 8,
                        border=1, border_color=(100, 72, 12))
        # Title
        sb_title = self.f_small.render("HIGH SCORES", True, C_GOLD)
        surf.blit(sb_title, sb_title.get_rect(center=(sb_x + sb_w // 2, sb_y + 14)))
        pygame.draw.line(surf, C_DARK_GOLD, (sb_x + 8, sb_y + 24), (sb_x + sb_w - 8, sb_y + 24), 1)
        if not self.high_scores:
            empty = self.f_tiny.render("no scores yet", True, (100, 80, 30))
            surf.blit(empty, empty.get_rect(center=(sb_x + sb_w // 2, sb_y + 42)))
        else:
            for ri, (sc2, st2, dl2) in enumerate(self.high_scores[:8]):
                ry = sb_y + 32 + ri * 20
                rank_col = C_GOLD if ri == 0 else (C_WHITE if ri < 3 else (140, 110, 50))
                medal = ("#1", "#2", "#3")[ri] if ri < 3 else f"#{ri+1}"
                rk = self.f_tiny.render(medal, True, rank_col)
                surf.blit(rk, (sb_x + 8, ry))
                sc_t2 = self.f_tiny.render(f"{sc2:,}", True, rank_col)
                surf.blit(sc_t2, (sb_x + 34, ry))
                info = self.f_tiny.render(f"{st2:.0f}s  d{dl2}", True, (100, 80, 30))
                surf.blit(info, (sb_x + 100, ry))
        # Last score highlight
        if self.last_score:
            ls = self.last_score
            ls_y = sb_y + sb_h + 6
            ls_bg = pygame.Surface((sb_w, 18), pygame.SRCALPHA)
            ls_bg.fill((40, 20, 0, 160))
            surf.blit(ls_bg, (sb_x, ls_y))
            ls_t = self.f_tiny.render(f"LAST: {ls[0]:,}  ({ls[1]:.0f}s, drunk {ls[2]})", True, C_DARK_GOLD)
            surf.blit(ls_t, ls_t.get_rect(center=(sb_x + sb_w // 2, ls_y + 9)))

        # ── CONTROLS FOOTER ───────────────────────────────────────────────────
        ctrl_y = H - 36
        ctrl_bg = pygame.Surface((W, 40), pygame.SRCALPHA)
        ctrl_bg.fill((0, 0, 0, 145))
        surf.blit(ctrl_bg, (0, ctrl_y - 4))
        for ci, txt in enumerate(["← → : CHOOSE", "ENTER : ORDER", "BACKSPACE : SEND BACK", "R : RIDE!"]):
            ct = self.f_tiny.render(txt, True, C_DARK_GOLD)
            surf.blit(ct, (18 + ci * 218, ctrl_y))
        btn_col = C_DARK_GOLD if self.drink_history else (52, 32, 6)
        draw_round_rect(surf, btn_col, (W-168, ctrl_y-6, 152, 34), 6)
        bt2 = self.f_med.render("LET'S RIDE!  R", True, C_DARK if self.drink_history else (85, 60, 18))
        surf.blit(bt2, bt2.get_rect(center=(W-92, ctrl_y+11)))


    # ─────────────────────────────────────────────────────────────────────────
    #  RACE PHASE
    # ─────────────────────────────────────────────────────────────────────────
    def _race_keydown(self, key):
        """Handle key presses during the race. Instead of acting immediately,
        each press is pushed onto input_queue with a fire time of
        (current_frame + delay_frames). The queue is drained by
        _process_input_queue each frame.

        Delay formula: fx_delay × 3 frames per vodka drink.
        At 60 fps that gives ~50ms per vodka, capping at ~500ms for 10 vodkas.
        This simulates the slowed reflexes of a very drunk jockey."""
        delay_frames = self.fx_delay * 3   # vodka: 3 frames per drink — 10 vodkas = ~500ms
        if key == pygame.K_LEFT:
            self.input_queue.append((self.race_frame + delay_frames, "left"))
        elif key == pygame.K_RIGHT:
            self.input_queue.append((self.race_frame + delay_frames, "right"))
        elif key == pygame.K_UP:
            self.input_queue.append((self.race_frame + delay_frames, "jump"))


    def _process_input_queue(self):
        """Fire any queued inputs whose delay has expired.
        Items that haven't reached their fire_at frame are kept for next time."""
        remaining = []
        for (fire_at, action) in self.input_queue:
            if self.race_frame >= fire_at:
                if action == "left":
                    self.player_lane = max(0, self.player_lane - 1)
                elif action == "right":
                    self.player_lane = min(2, self.player_lane + 1)
                elif action == "jump" and not self.is_jumping:
                    self.is_jumping = True
                    self.jump_vel   = -22.0   # increased for higher arc
            else:
                remaining.append((fire_at, action))
        self.input_queue = remaining

    def _spawn_wave(self, spawn_depth: float):
        """Spawn a wave of obstacles that is ALWAYS survivable.

        A wave is built by first choosing which lanes are *blocked*, then
        checking that guards don't cover every escape route.  Guards spawned
        as part of a wave are staggered slightly ahead so the player sees the
        obstacle first and the guard second — never both arriving together.
        """
        # roll is a single random float [0, 1) that decides the wave type.
        # The four outcomes (triple fence, single, double, lone guard) have
        # different probability thresholds. Triple fence is gated behind drunk
        # level 3+ so sober players never face it.
        roll = random.random()

        # Triple fence only appears when drunk (drunk_level ≥ 3)
        triple_threshold = 0.15 if self.drunk_level >= 3 else 0.0

        if roll < triple_threshold:
            # ── TRIPLE FENCE (drunk only) ──────────────────────────────────────
            # All 3 lanes get a fence, but one is a ghost (drawn semi-transparent).
            # Sober players see it clearly as faded — the safe path is obvious.
            # Drunk players see the ghost almost as solid as the real fences,
            # making it genuinely difficult to identify the passable lane.
            ghost_lane = random.randint(0, 2)
            for lane in range(3):
                obs = Obstacle(lane, OBS_TYPES[0], spawn_depth=spawn_depth)
                obs.is_ghost = (lane == ghost_lane)
                self.obstacles.append(obs)
            # No guard with triple fence — the fence puzzle is hard enough

        elif roll < 0.55:
            # ── SINGLE OBSTACLE (55% of waves when not triple) ────────────────
            # The simplest wave: one obstacle in one random lane. A guard may
            # optionally co-spawn in a different lane (22% chance), but ONLY if
            # there are still at least 2 free lanes — guaranteeing one safe path.
            otype = random.choice(OBS_TYPES)
            lane  = random.randint(0, 2)
            obs   = Obstacle(lane, otype, spawn_depth=spawn_depth)
            obs.is_ghost = False
            self.obstacles.append(obs)

            # Guard may co-spawn but MUST NOT block all remaining open lanes.
            # Open lanes after the obstacle: all lanes except obs.lane
            if random.random() < 0.22:
                open_lanes = [l for l in range(3) if l != lane]
                # Guard takes one open lane — player always has at least one other
                if len(open_lanes) >= 2:
                    guard_lane = random.choice(open_lanes)
                    g = Guard(random.randint(0, 2))
                    g.lane = guard_lane
                    # Stagger guard slightly closer so obstacle arrives first
                    g.depth = min(spawn_depth, 0.88)
                    self.guards.append(g)

        elif roll < 0.80:
            # ── DOUBLE OBSTACLE (25% of non-triple waves) ─────────────────────
            # Two obstacles in two different lanes. Exactly one lane is safe.
            # A guard can only spawn in an already-blocked lane (it's redundant
            # there), so it never reduces the number of safe paths.
            blocked = random.sample(range(3), 2)
            safe    = [l for l in range(3) if l not in blocked][0]
            for lane in blocked:
                otype = random.choice(OBS_TYPES)
                obs   = Obstacle(lane, otype, spawn_depth=spawn_depth)
                obs.is_ghost = False
                self.obstacles.append(obs)

            # Guard ONLY allowed if it goes into a blocked lane (it's already
            # lethal, so it won't add a new threat) — effectively decorative,
            # or skip the guard entirely.  Never put guard in the safe lane.
            if random.random() < 0.18:
                guard_lane = random.choice(blocked)
                g = Guard(guard_lane)
                g.depth = min(spawn_depth, 0.85)
                self.guards.append(g)

        else:
            # ── LONE GUARD (20% of non-triple waves) ──────────────────────────
            # Just a security guard, no obstacle. Tests the player's ability to
            # dodge a moving enemy without the added pressure of an obstacle.────
            g = Guard(random.randint(0, 2))
            self.guards.append(g)

    def _update_race(self):
        """Core race logic executed every frame. Order of operations:
          1. Advance time counters and calculate base speed/spawn interval
          2. Spawn a new obstacle wave if the spawn timer fires
          3. Apply jump physics
          4. Spawn/update dust particles
          5. Apply whiskey speed bonus (overwrites base speed)
          6. Apply cider wobble/stumble
          7. Process the delayed input queue
          8. Move all obstacles and guards, prune those that have passed
          9. Check for collisions — transition to GAME OVER if hit
          10. Advance bg_offset (drives track stripe scrolling + sticker scroll)
        """
        self.race_frame  += 1
        self.survive_time = self.race_frame / FPS  # time in seconds
        self.base_score   = int(self.survive_time * 10)  # 10 points per second survived

        # Game speed increases gradually over time — the longer you survive the
        # faster obstacles approach. Whiskey adds a further bonus (step 5 below).
        self.game_speed    = 0.010 + self.survive_time * 0.00013
        # Spawn interval shrinks over time (more frequent waves), floor at 32 frames.
        self.spawn_interval = max(32, 80 - self.survive_time * 1.0)

        # ── Spawn timer ───────────────────────────────────────────────────────
        # Each wave is designed to be survivable: at least one lane is always
        # free of both obstacles and guards. spawn_depth controls how far away
        # the obstacles appear — sober players get full warning (~1.5s), drunk
        # players get obstacles much closer (~0.7s at max drunk).
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            # Sober = obstacles appear near the horizon (lots of warning).
            # Drunk = they pop in much closer (less reaction time).
            # Formula: 0.98 at drunk_level=0, 0.70 at drunk_level=23+
            spawn_depth = max(0.70, 0.98 - self.drunk_level * 0.012)
            self._spawn_wave(spawn_depth)

        # ── Jump physics ─────────────────────────────────────────────────────
        # jump_vel starts negative (upward) and increases each frame (gravity).
        # When player_y returns to 0 the horse lands. Gravity scales with game
        # speed so at higher speeds the arc is proportionally shorter, preventing
        # the jump from feeling floaty when things are moving fast.
        if self.is_jumping:
            gravity         = 0.9 * (self.game_speed / 0.010)
            gravity         = max(0.30, gravity)   # never TOO floaty
            self.jump_vel  += gravity
            self.player_y  += self.jump_vel
            if self.player_y >= 0:
                self.player_y  = 0
                self.is_jumping = False
                self.jump_vel   = 0.0

        # ── PARTICLE SYSTEM ──────────────────────────────────────────────────
        px_ground = int(lane_to_x(self.player_lane, 0.0) + self.stumble_dx)

        # Takeoff burst when jump starts
        if self.is_jumping and not self._was_jumping:
            for _ in range(14):
                angle = random.uniform(math.pi, 2 * math.pi)
                spd   = random.uniform(2, 6)
                self.particles.append(dict(
                    x=px_ground, y=H - 18,
                    vx=math.cos(angle) * spd, vy=math.sin(angle) * spd - 2,
                    life=22, max_life=22, r=random.randint(2, 5),
                    color=(160, 128, 80)))
        self._was_jumping = self.is_jumping

        # Landing dust cloud
        if not self.is_jumping and self._was_jumping:
            for _ in range(22):
                angle = random.uniform(math.pi, 2 * math.pi)
                spd   = random.uniform(3, 9)
                self.particles.append(dict(
                    x=px_ground, y=H - 12,
                    vx=math.cos(angle) * spd, vy=math.sin(angle) * spd * 0.4,
                    life=28, max_life=28, r=random.randint(3, 7),
                    color=(140, 110, 65)))

        # Continuous hoof-kick particles while running
        if not self.is_jumping and random.random() < 0.25:
            side = random.choice((-1, 1))
            self.particles.append(dict(
                x=px_ground + side * random.randint(8, 22), y=H - 10,
                vx=side * random.uniform(0.5, 2.5), vy=random.uniform(-3, -1),
                life=14, max_life=14, r=random.randint(1, 3),
                color=(130, 100, 55)))

        # Update existing particles
        alive = []
        for p in self.particles:
            p['x']  += p['vx']
            p['y']  += p['vy']
            p['vy'] += 0.35   # gravity
            p['life'] -= 1
            if p['life'] > 0:
                alive.append(p)
        self.particles = alive

        # ── Drunk effects ──────────────────────────────────────────────────────
        # WHISKEY: adds a flat speed bonus on top of the time-based ramp.
        # Recomputed here (after jump physics) so the spawn interval calculated
        # above uses the non-whiskey speed; only movement uses the boosted speed.
        speed_bonus = self.fx_speed * 0.0015
        self.game_speed = (0.010 + self.survive_time * 0.00013) + speed_bonus

        # CIDER: sway_angle tilts the entire scene surface (like the world
        # is rocking). stumble_dx occasionally shoves the player sprite sideways.
        self.sway_angle    = math.sin(self.race_frame * 0.04) * self.fx_wobble * 0.013
        self.distort_phase += 0.05
        if self.fx_wobble >= 1:
            self.stumble_timer -= 1
            if self.stumble_timer <= 0:
                # Random stumble: 40% chance of a sideways lurch, 60% chance of recovery
                self.stumble_timer = random.randint(55, 130)
                self.stumble_dx    = (random.random() - 0.5) * 15 * self.fx_wobble                                      if random.random() < 0.4 else 0.0
        else:
            self.stumble_dx = 0.0   # no cider = no stumble

        self._process_input_queue()

        # ── Move all objects ──────────────────────────────────────────────────
        for obs in self.obstacles:
            obs.update(self.game_speed)   # decrements obs.depth by game_speed
        # Remove any obstacle that has passed depth 0 (gone behind the player)
        self.obstacles = [o for o in self.obstacles if o.depth > 0.0]

        for g in self.guards:
            g.update(self.game_speed, self.player_lane)  # also handles lane-switch AI
        # Same cleanup for guards
        self.guards = [g for g in self.guards if g.depth > 0.0]

        # ── Collision detection ────────────────────────────────────────────────
        # Only check objects whose depth is inside the hit window (0.0–0.13).
        # A jump clears an obstacle if the horse is high enough (player_y < –28)
        # AND the obstacle is jumpable (block_jump=False).
        for obs in self.obstacles:
            if obs.lane != self.player_lane:
                continue
            if getattr(obs, "is_ghost", False):
                continue   # ghost fence is passable
            if not (HIT_DEPTH_MIN <= obs.depth <= HIT_DEPTH_MAX):
                continue
            clear_jump = self.is_jumping and self.player_y < -28 and not obs.block_jump
            if not clear_jump:
                final = int(self.base_score * self.multiplier)
                self._record_score(final)
                self.state = self.STATE_GAMEOVER
                return

        for g in self.guards:
            if g.lane == self.player_lane and HIT_DEPTH_MIN <= g.depth <= HIT_DEPTH_MAX:
                final = int(self.base_score * self.multiplier)
                self._record_score(final)
                self.state = self.STATE_GAMEOVER
                return

        # bg_offset drives all scrolling visuals: track stripes, kerbing,
        # sponsor stickers on the arena wall. Scaled by 60 so that at the base
        # game_speed of 0.010 the value increments by 0.6 per frame.
        self.bg_offset += self.game_speed * 60


    # ─────────────────────────────────────────────────────────────────────────
    #  CUTSCENE (bar → race transition)
    # ─────────────────────────────────────────────────────────────────────────
    def _cutscene_advance(self):
        """Called when the player presses any key or clicks during a cutscene.
        If the current image is fading in or holding, jump to the fade-out.
        The fade-out will automatically advance to the next image (or start
        the race when all images have been shown)."""
        # Jump straight to fade-out regardless of current phase
        if self._cutscene_fade in ("in", "hold"):
            self._cutscene_fade  = "out"
            self._cutscene_timer = 0

    def _update_cutscene(self):
        """Advance the cutscene state machine one frame.
        State transitions:
          "in"   — alpha increases 6 units/frame (0→255 in ~42 frames ≈ 0.7s)
          "hold" — wait HOLD_FRAMES (160 frames ≈ 2.7s) then switch to "out"
          "out"  — alpha decreases 6 units/frame (255→0), then:
                     advance to next image ("in") or start race if last image
        """
        self._cutscene_timer += 1
        FADE_SPEED  = 6    # alpha change per frame (0–255 range)
        HOLD_FRAMES = 160  # frames to hold the fully-visible image (~2.7s at 60fps)

        if self._cutscene_fade == "in":
            self._cutscene_alpha = min(255, self._cutscene_alpha + FADE_SPEED)
            if self._cutscene_alpha >= 255:
                self._cutscene_fade  = "hold"
                self._cutscene_timer = 0

        elif self._cutscene_fade == "hold":
            if self._cutscene_timer >= HOLD_FRAMES:
                self._cutscene_fade  = "out"
                self._cutscene_timer = 0

        elif self._cutscene_fade == "out":
            self._cutscene_alpha = max(0, self._cutscene_alpha - FADE_SPEED)
            if self._cutscene_alpha <= 0:
                self._cutscene_idx += 1
                if self._cutscene_idx >= len(self._cutscene_images):
                    # All images shown — start race
                    self.state = self.STATE_RACE
                else:
                    self._cutscene_fade  = "in"
                    self._cutscene_timer = 0

    def _draw_cutscene(self):
        """Draw the current cutscene frame: black background with the current
        image faded in/out according to _cutscene_alpha (0=invisible, 255=opaque).
        A 'PRESS ANY KEY TO CONTINUE' hint appears once the image is mostly visible."""
        surf = self.screen
        surf.fill((0, 0, 0))  # black behind the image
        if self._cutscene_idx < len(self._cutscene_images):
            img = self._cutscene_images[self._cutscene_idx].copy()
            img.set_alpha(self._cutscene_alpha)
            surf.blit(img, (0, 0))
        # "tap to skip" hint
        if self._cutscene_alpha > 120:
            hint = self.f_tiny.render("PRESS ANY KEY TO CONTINUE", True,
                                      (180, 150, 80, self._cutscene_alpha))
            surf.blit(hint, hint.get_rect(center=(W // 2, H - 20)))

    def _record_score(self, final: int):
        """Append the final score to the in-memory leaderboard and keep only
        the top 8 entries. Also stores the score as last_score so it can be
        highlighted in the bar scoreboard on the next visit.
        Scores are not saved to disk — they reset when the program closes."""
        self.last_score = (final, self.survive_time, self.drunk_level)
        self.high_scores.append(self.last_score)
        self.high_scores.sort(key=lambda x: -x[0])
        self.high_scores = self.high_scores[:8]

    def _draw_race(self):
        """Compose and draw one race frame.

        Rendering pipeline:
          1. Draw the full track background onto a temp surface (scene)
          2. Draw all obstacles and guards back-to-front (painter's algorithm)
          3. Draw the player horse + jockey
          4. Draw dust particles on top of the player
          5. Apply cider blur (BEER) and vignette (CIDER) overlays to scene
          6. Rotate/offset scene by the cider sway angle and stumble offset
          7. Blit the final scene to the real screen
          8. Draw the HUD on top (HUD is never rotated)
        """
        surf = self.screen

        # ── Camera sway (cider effect) ────────────────────────────────────────
        # sway_x is the horizontal pixel shift applied to the rotated scene.
        # The entire scene is rotated by sway_angle (set in _update_race) so the
        # whole world tilts, then shifted sideways by stumble_dx for lurching.
        sway_x = math.sin(self.race_frame * 0.055) * self.fx_wobble * 3 + self.stumble_dx * 0.3
        # All racing visuals are rendered onto this intermediate surface so we
        # can rotate the whole scene in one operation at the end.
        scene = pygame.Surface((W, H))

        self._draw_track_bg(scene)

        # ── Painter's algorithm — draw far objects first ─────────────────────
        # Obstacles and guards at high depth (near the horizon) are drawn before
        # those at low depth (near the camera), so closer objects correctly appear
        # in front of farther ones. Both lists are merged then sorted descending.
        all_objs = [(obs.depth, obs, "obs") for obs in self.obstacles] +                    [(g.depth,   g,   "grd") for g   in self.guards]
        all_objs.sort(key=lambda x: -x[0])  # highest depth first = furthest first
        for _, obj, kind in all_objs:
            if kind == "obs":
                obj.draw(scene, drunk_level=self.drunk_level)  # ghost alpha
            else:
                obj.draw(scene)

        self._draw_player(scene)

        # ── PARTICLES ────────────────────────────────────────────────────────
        for p in self.particles:
            frac  = p['life'] / p['max_life']
            alpha = int(200 * frac)
            r     = max(1, int(p['r'] * frac))
            ps    = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(ps, p['color'] + (alpha,), (r + 1, r + 1), r)
            scene.blit(ps, (int(p['x']) - r - 1, int(p['y']) - r - 1))

        # ── Per-drink visual effect overlays ─────────────────────────────────
        # These are applied to the scene surface before rotation so they
        # also tilt with the world when cider is active.
        # CIDER: dark circular vignette around the screen edges (tunnel-vision)
        if self.fx_wobble >= 1:
            vig   = pygame.Surface((W, H), pygame.SRCALPHA)
            alpha = min(160, self.fx_wobble * 18)
            for radius in range(W // 2, W // 2 - 80, -8):
                a = max(0, int((1 - radius / (W / 2)) * alpha * 2))
                pygame.draw.circle(vig, (0, 0, 0, a), (W // 2, H // 2), radius, 8)
            scene.blit(vig, (0, 0))

        # BEER: blur by downscaling then upscaling the scene surface.
        # The blur divisor shrinks the intermediate surface more at higher stack.
        # A semi-transparent blurred copy is blitted on top to achieve a soft focus.
        if self.fx_blur >= 1:
            blur_divisor = max(2, 11 - self.fx_blur // 2)   # 1 beer=÷10, 10 beers=÷6
            small   = pygame.transform.smoothscale(scene, (W // blur_divisor, H // blur_divisor))
            blurred = pygame.transform.smoothscale(small, (W, H))
            blurred.set_alpha(min(210, self.fx_blur * 24))
            scene.blit(blurred, (0, 0))

        # ── Apply rotation + horizontal shift, then blit to screen ───────────
        # pygame.transform.rotate returns a larger surface (to fit the rotated
        # content), so we must re-centre it on the screen after rotating.
        angle_deg = math.degrees(self.sway_angle)
        rotated   = pygame.transform.rotate(scene, angle_deg)
        rx = W // 2 - rotated.get_width()  // 2 + int(sway_x)
        ry = H // 2 - rotated.get_height() // 2
        surf.blit(rotated, (rx, ry))

        self._draw_hud(surf)

    def _draw_track_bg(self, surf):
        """Draw all 11 layers of the race track background in order.
        Layers are numbered 1–11 from back to front:
          1.  Sky gradient (dusk colours, dark top to warm amber horizon)
          2.  Floodlight light cones (semi-transparent triangles)
          3.  Stadium stands (dark block + tier lines + animated crowd dots)
          4.  Floodlight pylons (metal poles + lamp heads + glow halos)
          5.  Advertising boards (fixed coloured panels with text)
          6.  Ground / arena dirt gradient (fills everything below horizon)
          7.  Track surface (alternating stripe quads, scroll with bg_offset)
          8.  Concrete arena walls (left + right kerb barriers with perspective)
          9.  Red/white kerbing (alternating segments on track edges)
          10. Lane divider lines (solid outer + dashed centre)
          11. Horizon line (thin dark line at vanishing point)
        Everything is drawn directly onto `surf` (the scene surface), NOT the
        real screen — the caller applies rotation and blits to screen afterward.
        """
        # ── 1. SKY — evening stadium dusk gradient ───────────────────────────
        C_SKY_A = (22, 18, 36)
        C_SKY_B = (80, 45, 20)
        C_SKY_C = (160, 90, 30)
        for i in range(HORIZON_Y):
            t = i / HORIZON_Y
            if t < 0.5:
                t2  = t * 2
                col = tuple(int(C_SKY_A[c] + (C_SKY_B[c] - C_SKY_A[c]) * t2) for c in range(3))
            else:
                t2  = (t - 0.5) * 2
                col = tuple(int(C_SKY_B[c] + (C_SKY_C[c] - C_SKY_B[c]) * t2) for c in range(3))
            pygame.draw.line(surf, col, (0, i), (W, i))

        # ── 2. FLOODLIGHT CONES ──────────────────────────────────────────────
        # Semi-transparent light cone triangles emanating from the floodlight
        # pylons at either side of the stands. Drawn as alpha polygons.
        for lx in (65, W - 65):
            cone = pygame.Surface((260, HORIZON_Y + 60), pygame.SRCALPHA)
            tip_x = 130
            pygame.draw.polygon(cone, (255, 240, 180, 18),
                                 [(tip_x, 0), (0, HORIZON_Y + 60), (260, HORIZON_Y + 60)])
            surf.blit(cone, (lx - 130, 0))

        # ── 3. STADIUM STANDS + CROWD ────────────────────────────────────────
        # Two overlapping dark rectangles fill the sky behind the horizon with
        # stadium seating. Horizontal tier lines give depth. On top of the tiers,
        # 520 coloured dots represent crowd members; each dot bobs up and down
        # on a travelling sine wave (simulating the crowd roar / Mexican wave).
        stand_top_y = 10
        stand_bot_y = HORIZON_Y - 2
        stand_h     = stand_bot_y - stand_top_y
        pygame.draw.rect(surf, (28, 22, 40), (0, stand_top_y, W // 2 + 30, stand_h))
        pygame.draw.rect(surf, (24, 18, 36), (W // 2 - 30, stand_top_y, W // 2 + 30, stand_h))
        for tier in range(8):
            ty  = stand_top_y + int(stand_h * tier / 8)
            col = (35 + tier * 2, 28 + tier * 2, 50 + tier * 2)
            pygame.draw.line(surf, col, (0, ty), (W, ty), 1)

        # Crowd dots — animated wave (roar effect)
        crowd_cols = [(220,50,50),(50,180,220),(240,200,40),
                      (180,80,220),(60,220,100),(255,255,255),(240,120,40)]
        rng = random.Random(42)
        crowd_data = []
        for _ in range(520):
            crowd_data.append((
                rng.randint(0, W),
                rng.randint(stand_top_y + 6, stand_bot_y - 4),
                crowd_cols[rng.randint(0, len(crowd_cols) - 1)],
                rng.randint(1, 3),
                rng.uniform(0, math.pi * 2),   # phase offset
            ))
        t_crowd = self.race_frame * 0.06
        for (fx, fy, fc, fr, phase) in crowd_data:
            # Each person bobs up and down slightly, wave travels left→right
            wave = math.sin(t_crowd + fx * 0.018 + phase)
            bob  = int(wave * 2.5)
            # Brightness pulses with the wave (arms up = brighter)
            bright = int(max(0, wave) * 40)
            c = tuple(min(255, ch + bright) for ch in fc)
            pygame.draw.circle(surf, c, (fx, fy + bob), fr)

        # ── 4. FLOODLIGHT PYLONS ─────────────────────────────────────────────
        # Two steel pylons (one each side) with a horizontal arm at the top
        # bearing 4 lamp heads each. Each lamp has a soft yellow glow halo.
        for lx in (55, W - 55):
            pygame.draw.rect(surf, (55, 55, 65), (lx - 5, 20, 10, HORIZON_Y - 20))
            pygame.draw.rect(surf, (70, 70, 80), (lx - 2, 20, 4,  HORIZON_Y - 20))
            arm_len = 36
            pygame.draw.rect(surf, (55, 55, 65), (lx - arm_len, 24, arm_len * 2, 5))
            for li in range(4):
                lhx = lx - arm_len + 8 + li * (arm_len * 2 - 16) // 3
                pygame.draw.ellipse(surf, (255, 245, 200), (lhx - 5, 16, 10, 10))
                gl = pygame.Surface((20, 20), pygame.SRCALPHA)
                pygame.draw.ellipse(gl, (255, 240, 160, 60), (0, 0, 20, 20))
                surf.blit(gl, (lhx - 10, 11))

        # ── 5. ADVERTISING BOARDS ────────────────────────────────────────────
        # 10 coloured panels sit just above the horizon line (the "hoarding"
        # behind the track). They are evenly spaced and centred across the full
        # screen width. Text alternates between "THE DERBY", "DRINK RESPONSIBLY"
        # and other race-day slogans. Each board has a brighter top highlight.
        board_h = 20
        board_y = HORIZON_Y - board_h - 2
        board_colors = [
            (200, 30,  30),   # red
            (30,  100, 200),  # blue
            (220, 180,  0),   # gold
            (30,  160,  30),  # green
            (200,  80, 200),  # purple
            (240, 120,   0),  # orange
            (18,   18,  18),  # near-black (Derby branding)
            (180,  20,  20),  # dark red (drink responsibly)
            (20,   80, 160),  # navy
            (160, 130,  20),  # dark gold
        ]
        board_texts = [
            "THE DERBY",
            "DRINK RESPONSIBLY",
            "THE DERBY",
            "GOLD CUP 2025",
            "DRINK RESPONSIBLY",
            "THE DERBY",
            "VIP ZONE",
            "DRINK RESPONSIBLY",
            "THE DERBY",
            "RACE DAY",
            "DRINK RESPONSIBLY",
            "BET NOW",
        ]
        board_w = 128
        n_boards = 10
        total_w  = n_boards * board_w + (n_boards - 1) * 4
        start_x  = (W - total_w) // 2
        for bi in range(n_boards):
            bx  = start_x + bi * (board_w + 4)
            col = board_colors[bi % len(board_colors)]
            txt_str = board_texts[bi % len(board_texts)]
            pygame.draw.rect(surf, col, (bx, board_y, board_w, board_h))
            # Highlight top stripe
            hi = tuple(min(255, c + 55) for c in col)
            pygame.draw.rect(surf, hi, (bx, board_y, board_w, 3))
            pygame.draw.rect(surf, (255, 255, 255), (bx, board_y, board_w, board_h), 1)
            txt = self.f_tiny.render(txt_str, True, (255, 255, 255))
            surf.blit(txt, txt.get_rect(center=(bx + board_w // 2, board_y + board_h // 2)))

        # ── 6. GROUND GRADIENT ───────────────────────────────────────────────
        # Fills the entire area below the horizon with a dark-amber-to-brown
        # gradient. The track stripes are drawn on top of this (step 7).
        dirt_top = (110, 88, 55)
        dirt_bot = (75,  58, 32)
        for i in range(HORIZON_Y, H):
            t   = (i - HORIZON_Y) / (H - HORIZON_Y)
            col = tuple(int(dirt_top[c] + (dirt_bot[c] - dirt_top[c]) * t) for c in range(3))
            pygame.draw.line(surf, col, (0, i), (W, i))

        # ── 7. TRACK SURFACE ─────────────────────────────────────────────────
        # The track is drawn as alternating light/dark trapezoid stripes that
        # scroll toward the player each frame (using bg_offset). Each stripe is
        # a perspective-correct quad whose four corners are computed using
        # lane_to_x / depth_to_y for two consecutive depth values.
        edge_off = 0.55  # how far the track extends beyond the outer lane centres
        def track_edges(depth):
            """Return the left and right x-pixel edges of the full track at this depth."""
            lx = lane_to_x(0, depth) - lane_pixel_width(depth) * edge_off
            rx = lane_to_x(2, depth) + lane_pixel_width(depth) * edge_off
            return lx, rx

        C_TRACK_A = (130, 105, 68)
        C_TRACK_B = (118,  94, 58)
        stripe_count = 22
        scroll_frac  = (self.bg_offset * 0.022) % (1.0 / stripe_count)
        for i in range(stripe_count + 2):
            d0 = max(0.0, (i / stripe_count) - scroll_frac)
            d1 = max(0.0, ((i + 1) / stripe_count) - scroll_frac)
            if d0 >= 1.0:
                continue
            d1 = min(d1, 1.0)
            lx0, rx0 = track_edges(d0)
            lx1, rx1 = track_edges(d1)
            y0 = depth_to_y(d0)
            y1 = depth_to_y(d1)
            col = C_TRACK_A if i % 2 == 0 else C_TRACK_B
            pygame.draw.polygon(surf, col, [(lx1,y1),(rx1,y1),(rx0,y0),(lx0,y0)])

        # ── 8. ARENA WALLS + SPONSOR STICKERS ────────────────────────────────
        # Low concrete barriers run along both sides of the track. Each wall
        # segment is drawn as two quads: a vertical face and a horizontal top
        # surface, both perspective-correct. Coloured sponsor stickers scroll
        # along the left wall to fill empty space.
        wall_h_frac = 0.12
        wall_col  = (180, 170, 155)
        wall_hi   = (210, 200, 185)
        for side in range(2):
            for depth_i in range(20):
                d0 = depth_i / 20
                d1 = (depth_i + 1) / 20
                if d0 >= 1.0:
                    continue
                lx0, rx0 = track_edges(d0)
                lx1, rx1 = track_edges(d1)
                lw0 = lane_pixel_width(d0)
                lw1 = lane_pixel_width(d1)
                wh0 = lw0 * wall_h_frac
                wh1 = lw1 * wall_h_frac
                y0  = depth_to_y(d0)
                y1  = depth_to_y(d1)
                if side == 0:
                    pts_face = [(lx1,y1),(lx0,y0),(lx0,y0-wh0),(lx1,y1-wh1)]
                    pts_top  = [(lx1,y1-wh1),(lx0,y0-wh0),
                                (lx0-lw0*0.05,y0-wh0),(lx1-lw1*0.05,y1-wh1)]
                else:
                    pts_face = [(rx0,y0),(rx1,y1),(rx1,y1-wh1),(rx0,y0-wh0)]
                    pts_top  = [(rx0,y0-wh0),(rx1,y1-wh1),
                                (rx1+lw1*0.05,y1-wh1),(rx0+lw0*0.05,y0-wh0)]
                if len(pts_face) >= 3:
                    pygame.draw.polygon(surf, wall_col, pts_face)
                    pygame.draw.polygon(surf, wall_hi,  pts_top)

        # Sponsor stickers on left wall
        sticker_cols = [(200,30,30),(30,80,200),(220,180,0)]
        for si in range(6):
            d = (si / 5 - (self.bg_offset * 0.022) % (1.0/5)) % 1.0
            if d < 0.05 or d > 0.95:
                continue
            lx, _ = track_edges(d)
            lw2    = lane_pixel_width(d)
            wh     = lw2 * wall_h_frac
            sy     = depth_to_y(d)
            sw2    = max(4, int(lw2 * 0.25))
            sh2    = max(2, int(wh  * 0.6))
            sc_col = sticker_cols[si % len(sticker_cols)]
            pygame.draw.rect(surf, sc_col,
                             (int(lx - sw2 // 2 - lw2 * 0.03), int(sy - wh * 0.8), sw2, sh2))

        # ── 9. KERBING ───────────────────────────────────────────────────────
        # Red and white alternating blocks on both track edges, scrolling with
        # bg_offset. Each segment is a perspective-correct trapezoid.
        kerb_count = 16
        for i in range(kerb_count + 2):
            d_off = (self.bg_offset * 0.022) % (1.0 / kerb_count)
            d0 = max(0.0, (i / kerb_count) - d_off)
            d1 = max(0.0, ((i+1)/kerb_count) - d_off)
            if d0 >= 1.0:
                continue
            d1 = min(d1, 0.99)
            kerb_col = (210,35,35) if i % 2 == 0 else (240,240,240)
            lx0, rx0 = track_edges(d0)
            lx1, rx1 = track_edges(d1)
            kw0 = lane_pixel_width(d0) * 0.16
            kw1 = lane_pixel_width(d1) * 0.16
            y0, y1 = depth_to_y(d0), depth_to_y(d1)
            pygame.draw.polygon(surf, kerb_col, [(lx1-kw1,y1),(lx1,y1),(lx0,y0),(lx0-kw0,y0)])
            pygame.draw.polygon(surf, kerb_col, [(rx1,y1),(rx1+kw1,y1),(rx0+kw0,y0),(rx0,y0)])

        # ── 10. LANE DIVIDERS ─────────────────────────────────────────────────
        # Solid lines mark the outer edges of the track (hard walls).
        # Dashed lines between lanes show the lane boundaries the player can
        # switch between. Dashes scroll with bg_offset to show movement.
        for side_lane, side_off in [(0, -0.5), (2, 0.5)]:
            near_x = int(lane_to_x(side_lane, 0.0)  + lane_pixel_width(0.0)  * side_off)
            far_x  = int(lane_to_x(side_lane, 0.97) + lane_pixel_width(0.97) * side_off)
            pygame.draw.line(surf, (220,210,180), (far_x, HORIZON_Y), (near_x, H), 3)

        dash_d_span = 0.065
        gap_frac    = 0.45
        for gap_lane in range(2):
            d_off = (self.bg_offset * 0.022) % dash_d_span
            for step in range(18):
                d_start = step * dash_d_span - d_off
                d_end   = d_start + dash_d_span * gap_frac
                d_start = max(0.01, d_start)
                d_end   = min(0.98, d_end)
                if d_start >= d_end:
                    continue
                x0 = int((lane_to_x(gap_lane, d_start) + lane_to_x(gap_lane+1, d_start)) / 2)
                x1 = int((lane_to_x(gap_lane, d_end)   + lane_to_x(gap_lane+1, d_end))   / 2)
                y0 = int(depth_to_y(d_start))
                y1 = int(depth_to_y(d_end))
                lw = max(1, int(lane_pixel_width(d_start) * 0.06))
                pygame.draw.line(surf, (230,220,180), (x0,y0), (x1,y1), lw)

        # ── 11. HORIZON LINE ─────────────────────────────────────────────────
        # A single thin dark line at HORIZON_Y to sharpen the ground/sky boundary.
        pygame.draw.line(surf, (50, 38, 22), (0, HORIZON_Y), (W, HORIZON_Y), 2)


    def _draw_player(self, surf):
        """Draw the player's horse and jockey viewed almost head-on (the camera
        is directly behind them). Because we see them from the front:
          - The horse body is tall and narrow (depth-foreshortened)
          - All four legs drop downward and splay slightly outward
          - The large head faces the camera with wide-set eyes
          - The jockey sits on the withers in a forward crouch

        The jockey is styled to match the cutscene character:
        red jumper, black trousers, black riding helmet, pale skin, dark hair.

        bob   — a gentle sine oscillation added to base_y for gallop rhythm
        gait  — a faster oscillation used to animate the leg swing
        """
        px     = int(lane_to_x(self.player_lane, 0.0) + self.stumble_dx)  # screen X, with cider stumble offset
        ground = H - 8        # pixel row where the hooves rest
        jy     = int(self.player_y)  # negative when in the air (jump)
        t      = self.bg_offset      # used as the animation clock
        bob    = int(math.sin(t * 0.52) * 3)   # gentle up-down gallop bob (±3px)
        base_y = ground + jy + bob   # combined ground position — moves up during jumps

        horse_c  = (72, 44, 18)           # chestnut body
        horse_hi = (105, 65, 28)          # lighter chest highlight
        leg_c    = (55, 32, 10)           # leg colour
        hoof_c   = (22, 14, 4)            # dark hooves
        gait     = t * 0.60              # gallop cycle

        # ── GROUND SHADOW ────────────────────────────────────────────────────
        sh_sc = max(0.2, 1.0 - abs(jy) / 140)
        sw    = int(96 * sh_sc)
        sh_s  = pygame.Surface((sw * 2, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh_s, (0, 0, 0, int(70 * sh_sc)), (0, 0, sw * 2, 10))
        surf.blit(sh_s, (px - sw, ground - 3))

        # ── LEG GEOMETRY ─────────────────────────────────────────────────────
        # Four legs animate using sine waves with phase offsets so opposite legs
        # move together (rear-left with front-right, etc.) — a simplified gallop.
        # Each leg has three segments: upper leg (hip→knee), cannon bone (knee→foot),
        # fetlock bump, and hoof ellipse. All positions are offset from base_y.
        # Hip attachment points on the barrel
        body_top = base_y - 220          # top of barrel (scaled for 720p)
        body_bot = base_y - 96           # bottom of barrel
        barrel_cx = px
        barrel_half_w = 32               # half-width of slim barrel at mid

        # Hip sockets (where upper leg meets barrel)
        hip_pts = [
            (barrel_cx - 26, body_bot - 7),   # left rear
            (barrel_cx + 26, body_bot - 7),   # right rear
            (barrel_cx - 16, body_bot + 3),   # left front
            (barrel_cx + 16, body_bot + 3),   # right front
        ]
        # Phase offsets create a diagonal gait: rear-left (0) and front-right
        # (π/2) move together, rear-right (π) and front-left (3π/2) move together.
        phases = [0, math.pi, math.pi * 0.5, math.pi * 1.5]

        for i, (hx, hy) in enumerate(hip_pts):
            swing = math.sin(gait + phases[i])
            # Knee: swings forward/back ±12 px, drops to roughly mid-shin
            kx = hx + swing * 14
            ky = hy + 54
            # Cannon bone: nearly vertical, tiny splay outward
            side_sign = -1 if i % 2 == 0 else 1
            foot_x = kx + side_sign * 6 + swing * 6
            foot_y = base_y - 2

            # Upper leg (thick)
            pygame.draw.line(surf, leg_c, (hx, hy), (int(kx), int(ky)), 10)
            # Cannon bone (thinner)
            pygame.draw.line(surf, leg_c, (int(kx), int(ky)), (int(foot_x), foot_y), 7)
            # Fetlock bump
            pygame.draw.circle(surf, leg_c, (int(foot_x), foot_y - 2), 4)
            # Hoof
            pygame.draw.ellipse(surf, hoof_c,
                                (int(foot_x) - 8, foot_y - 4, 16, 9))

        # ── BARREL (body) — tall narrow ellipse, foreshortened ───────────────
        barrel_w = 64
        barrel_h = body_bot - body_top
        pygame.draw.ellipse(surf, horse_c,
                            (barrel_cx - barrel_w // 2, body_top,
                             barrel_w, barrel_h))
        # Chest highlight — lighter oval on the front face
        pygame.draw.ellipse(surf, horse_hi,
                            (barrel_cx - barrel_w // 4, body_top + 10,
                             barrel_w // 2, barrel_h // 3))

        # ── NECK — rises from centre-top of barrel ────────────────────────────
        neck_bot_x = barrel_cx
        neck_bot_y = body_top + 8
        neck_top_x = barrel_cx + 2      # very slight forward lean
        neck_top_y = body_top - 54
        neck_w = 28
        # Draw as a quad (trapezoid widening at base)
        pygame.draw.polygon(surf, horse_c, [
            (neck_bot_x - neck_w // 2,     neck_bot_y),
            (neck_bot_x + neck_w // 2,     neck_bot_y),
            (neck_top_x + neck_w // 2 - 4, neck_top_y),
            (neck_top_x - neck_w // 2 + 4, neck_top_y),
        ])
        # Neck highlight
        pygame.draw.polygon(surf, horse_hi, [
            (neck_bot_x - 4, neck_bot_y),
            (neck_bot_x + 4, neck_bot_y),
            (neck_top_x + 2, neck_top_y),
            (neck_top_x - 2, neck_top_y),
        ])

        # ── HEAD — front-on: wide jaw, long nose, big eyes ────────────────────
        head_cx = neck_top_x
        head_jaw_y = neck_top_y          # jaw attaches at neck top
        head_h  = 72
        head_w  = 42                     # scaled for 720p
        # Skull / forehead (upper, rounder)
        skull_y = head_jaw_y - head_h
        pygame.draw.ellipse(surf, horse_c,
                            (head_cx - head_w // 2, skull_y,
                             head_w, head_h))
        # Jaw flares slightly wider
        jaw_w = head_w + 8
        pygame.draw.ellipse(surf, horse_c,
                            (head_cx - jaw_w // 2, head_jaw_y - 22,
                             jaw_w, 26))
        # Blaze (narrow white stripe, front-on)
        pygame.draw.ellipse(surf, (225, 218, 205),
                            (head_cx - 4, skull_y + 8, 8, head_h - 18))
        # Eyes: set wide on sides of skull, large and dark
        for ex in (-11, 11):
            ey = skull_y + 14
            pygame.draw.ellipse(surf, (18, 10, 2),  (head_cx + ex - 5, ey - 4, 10, 8))
            pygame.draw.circle(surf, (240, 220, 160), (head_cx + ex + 1, ey - 1), 2)
        # Nostrils — large, oval, front-on
        for nx in (-7, 7):
            pygame.draw.ellipse(surf, (40, 20, 6),
                                (head_cx + nx - 5, head_jaw_y - 14, 10, 7))
        # Muzzle band (bridle)
        pygame.draw.line(surf, (155, 115, 45),
                         (head_cx - jaw_w // 2 + 2, head_jaw_y - 16),
                         (head_cx + jaw_w // 2 - 2, head_jaw_y - 16), 2)
        # Brow band
        pygame.draw.line(surf, (155, 115, 45),
                         (head_cx - head_w // 2 + 2, skull_y + 12),
                         (head_cx + head_w // 2 - 2, skull_y + 12), 2)
        # Ears — narrow triangles
        for ex, lean in ((-8, -2), (8, 2)):
            pygame.draw.polygon(surf, horse_c, [
                (head_cx + ex - 4, skull_y + 5),
                (head_cx + ex + 4, skull_y + 5),
                (head_cx + ex + lean, skull_y - 12),
            ])
            pygame.draw.polygon(surf, (200, 160, 120), [
                (head_cx + ex - 2, skull_y + 5),
                (head_cx + ex + 2, skull_y + 5),
                (head_cx + ex + lean, skull_y - 8),
            ])
        # Forelock / mane tuft between ears
        mane_wave = int(math.sin(t * 0.38) * 3)
        for mi in range(5):
            mxp = head_cx - 4 + mi * 2
            pygame.draw.line(surf, (28, 14, 4),
                             (mxp, skull_y + 4),
                             (mxp + mane_wave, skull_y - 6 - mi * 2), 2)

        # ── JOCKEY — styled to match cutscene character ──────────────────────
        # Red top, black trousers, pale skin, dark hair, black helmet
        J_RED    = (200, 38, 38)     # red jumper
        J_BLACK  = (22,  18, 14)     # black trousers / helmet
        J_SKIN   = (225, 195, 160)   # pale skin
        J_HAIR   = (30,  20,  8)     # very dark brown hair
        J_HELM   = (28,  24, 20)     # near-black helmet shell
        J_VISOR  = (60,  80, 110)    # dark blue-grey visor strip

        jock_seat_y = body_top - 3
        arm_bob     = int(math.sin(t * 0.52) * 4)

        # ── Black riding trousers / seat ──────────────────────────────────────
        pygame.draw.ellipse(surf, J_BLACK,
                            (barrel_cx - 26, jock_seat_y - 14, 52, 22))

        # ── Torso — red top, slightly forward lean ────────────────────────────
        tor_bot = (barrel_cx, jock_seat_y - 2)
        tor_top = (barrel_cx,  jock_seat_y - 48 + arm_bob)
        # Body rect (slightly wider than a line, front-on)
        pygame.draw.polygon(surf, J_RED, [
            (tor_bot[0] - 14, tor_bot[1]),
            (tor_bot[0] + 14, tor_bot[1]),
            (tor_top[0] +  8, tor_top[1]),
            (tor_top[0] -  8, tor_top[1]),
        ])
        # Subtle shading on right side
        pygame.draw.polygon(surf, (160, 28, 28), [
            (tor_bot[0] + 5,  tor_bot[1]),
            (tor_bot[0] + 14, tor_bot[1]),
            (tor_top[0] + 8,  tor_top[1]),
            (tor_top[0] + 3,  tor_top[1]),
        ])

        # ── Arms — red sleeves reaching forward with reins ───────────────────
        ay = tor_top[1] + 10 + arm_bob
        for sign in (-1, 1):
            ax = barrel_cx + sign * 30
            # Upper arm (shoulder to elbow)
            pygame.draw.line(surf, J_RED,
                             (tor_top[0] + sign * 8, tor_top[1] + 5),
                             (ax, ay), 8)
            # Forearm (elbow to hand — black glove)
            pygame.draw.line(surf, J_BLACK,
                             (ax, ay),
                             (ax + sign * 6, ay + 8), 7)
            pygame.draw.circle(surf, J_BLACK, (ax + sign * 6, ay + 8), 5)
            # Rein lines
            pygame.draw.line(surf, (145, 108, 38),
                             (ax + sign * 4, ay + 6),
                             (head_cx + sign * 8, head_jaw_y - 14), 2)

        # ── Head ──────────────────────────────────────────────────────────────
        hr  = 15
        hcx = barrel_cx
        hcy = tor_top[1] - hr - 3

        # Neck (skin coloured)
        pygame.draw.rect(surf, J_SKIN,
                         (hcx - 5, hcy + hr - 4, 10, 10), border_radius=2)

        # Face — pale oval
        pygame.draw.ellipse(surf, J_SKIN,
                            (hcx - hr + 2, hcy - 4, (hr - 2) * 2, hr * 2 - 4))

        # Black helmet dome covering top half of head
        pygame.draw.ellipse(surf, J_HELM,
                            (hcx - hr - 1, hcy - hr - 2, hr * 2 + 2, hr + 6))
        # Helmet peak / brim jutting forward slightly
        pygame.draw.polygon(surf, J_HELM, [
            (hcx - hr - 2, hcy + 2),
            (hcx + hr + 2, hcy + 2),
            (hcx + hr + 5, hcy + 6),
            (hcx - hr - 4, hcy + 6),
        ])
        # Visor strip just below helmet brim
        pygame.draw.rect(surf, J_VISOR,
                         (hcx - hr + 1, hcy + 1, (hr - 1) * 2, 4),
                         border_radius=1)

        # Eyes — small, dark, determined expression
        blink = (int(t * 2.4) % 28 != 0)
        for ex_off in (-4, 4):
            pygame.draw.circle(surf, (35, 22, 10),
                               (hcx + ex_off, hcy + 5), 2)
            if blink:
                pygame.draw.circle(surf, (240, 200, 160),
                                   (hcx + ex_off + 1, hcy + 4), 1)

        # Dark hair visible below helmet at sides / back
        pygame.draw.ellipse(surf, J_HAIR,
                            (hcx - hr, hcy + 4, 6, 8))
        pygame.draw.ellipse(surf, J_HAIR,
                            (hcx + hr - 6, hcy + 4, 6, 8))
        # Hair tuft at back (flowing in wind)
        hair_wave = int(math.sin(t * 0.6) * 2)
        for hi2 in range(4):
            pygame.draw.line(surf, J_HAIR,
                             (hcx - 3 + hi2 * 2, hcy + 8),
                             (hcx - 6 + hi2 * 2 + hair_wave, hcy + 16 + hi2), 2)

        # ── LANE INDICATOR DOTS ───────────────────────────────────────────────
        # Three dots at the bottom of the screen show available lanes.
        # The active lane (player's current lane) is shown bright white.
        for i in range(3):
            dot_x  = int(lane_to_x(i, 0.0))
            active = (i == self.player_lane)
            pygame.draw.circle(surf, (0, 0, 0),   (dot_x, H - 13), 7)
            pygame.draw.circle(surf, C_WHITE if active else C_DARK_GOLD,
                               (dot_x, H - 13), 5)
            if active:
                pygame.draw.circle(surf, (255, 255, 255), (dot_x, H - 13), 3)

    def _draw_hud(self, surf):
        """Draw the race HUD directly onto the real screen (not the scene surface).
        The HUD is drawn after scene rotation so it never tilts with the cider sway.

        Layout:
          Top bar:    SCORE (left) | MULTIPLIER (centre) | TIME (right)
          Bottom-left: coloured pills for each active drunk effect
          Bottom-left: pending input counter if vodka delay is active
          Bottom-centre: "[ JUMP ]" label when in the air
          Bottom (first 5s): control hints that fade out
        """
        # ── Top HUD bar ───────────────────────────────────────────────────────
        hud_bg = pygame.Surface((W, 48), pygame.SRCALPHA)
        hud_bg.fill((0, 0, 0, 130))
        surf.blit(hud_bg, (0, 0))
        pygame.draw.line(surf, C_DARK_GOLD, (0, 48), (W, 48), 1)

        # Score (left)
        score = int(self.base_score * self.multiplier)
        sc_t  = self.f_large.render(f"SCORE  {score:,}", True, C_WHITE)
        surf.blit(sc_t, (16, 8))

        # Multiplier (centre)
        mult_col = (255, 120, 40) if self.multiplier >= 3.0 else \
                   C_GOLD         if self.multiplier >= 1.5 else C_WHITE
        mt = self.f_large.render(f"x{self.multiplier:.1f}", True, mult_col)
        surf.blit(mt, mt.get_rect(center=(W // 2, 24)))

        # Time (right)
        tt = self.f_large.render(f"{self.survive_time:.1f}s", True, C_WHITE)
        surf.blit(tt, (W - tt.get_width() - 16, 8))

        # ── Per-effect pills (bottom-left) ───────────────────────────────────
        # Only effects that are actually active (stack > 0) are shown.
        # Each pill shows the effect name and stack count in the effect's colour.
        active_fx = []
        if self.fx_blur:   active_fx.append(("BLUR",  f"x{self.fx_blur}",  (100, 160, 240)))
        if self.fx_wobble: active_fx.append(("WOBBLE",f"x{self.fx_wobble}",(220, 140,  50)))
        if self.fx_speed:  active_fx.append(("SPEED", f"x{self.fx_speed}", (240,  80,  80)))
        if self.fx_delay:  active_fx.append(("DELAY", f"x{self.fx_delay}", (170,  80, 220)))
        if active_fx:
            panel_w = 18 + len(active_fx) * 80
            dl_bg = pygame.Surface((panel_w, 28), pygame.SRCALPHA)
            dl_bg.fill((0, 0, 0, 130))
            surf.blit(dl_bg, (0, H - 28))
            for fi, (label, count, col) in enumerate(active_fx):
                lt = self.f_tiny.render(f"{label} {count}", True, col)
                surf.blit(lt, (8 + fi * 80, H - 20))
        if self.input_queue:
            wt = self.f_tiny.render(f"  {len(self.input_queue)} delayed...", True, (170, 80, 220))
            surf.blit(wt, (8, H - 42))

        # ── Jump / duck state (bottom-centre) ────────────────────────────────
        if self.is_jumping:
            jt = self.f_med.render("[ JUMP ]", True, (100, 180, 255))
            surf.blit(jt, jt.get_rect(center=(W // 2, H - 24)))


        # Controls reminder fading over first 5 seconds
        if self.survive_time < 5:
            alpha = int(220 * min(1.0, (5 - self.survive_time) / 2))
            ct_bg = pygame.Surface((W, 22), pygame.SRCALPHA)
            ct_bg.fill((0, 0, 0, alpha // 2))
            surf.blit(ct_bg, (0, H - 22))
            ct    = self.f_tiny.render("LEFT / RIGHT — change lane          UP — jump", True,
                                       (int(C_DARK_GOLD[0] * alpha / 220),
                                        int(C_DARK_GOLD[1] * alpha / 220),
                                        int(C_DARK_GOLD[2] * alpha / 220)))
            surf.blit(ct, ct.get_rect(center=(W // 2, H - 11)))

    # ─────────────────────────────────────────────────────────────────────────
    #  GAME OVER
    # ─────────────────────────────────────────────────────────────────────────
    def _draw_gameover(self):
        """Draw the game-over screen. Shows:
          - Dark background with CRT-style scanlines
          - GAME OVER title + "you were caught" subtitle
          - Final score (base × multiplier) in large font
          - Score breakdown: base, multiplier, time, active effects
          - Rank badge (CAUTIOUS / RISKY / RECKLESS / LEGENDARY)
          - Flashing restart prompt
        No update function — this is a static screen that waits for input."""
        surf = self.screen
        surf.fill((8, 3, 0))  # near-black with a warm tint

        # Scanline texture — horizontal lines every 3 pixels darken the background
        for y in range(0, H, 3):
            pygame.draw.line(surf, (0, 0, 0), (0, y), (W, y))

        # Panel
        pw, ph = 460, 360
        px, py = W // 2 - pw // 2, H // 2 - ph // 2
        draw_round_rect(surf, C_PANEL, (px, py, pw, ph), 12,
                        border=2, border_color=C_DARK_GOLD)

        # Title
        go_t = self.f_huge.render("GAME OVER", True, C_RED)
        surf.blit(go_t, go_t.get_rect(center=(W // 2, py + 56)))
        sub  = self.f_small.render("YOU WERE CAUGHT", True, C_DARK_GOLD)
        surf.blit(sub, sub.get_rect(center=(W // 2, py + 88)))

        # Score
        final = int(self.base_score * self.multiplier)
        fs_t  = self.f_huge.render(f"{final:,}", True, C_WHITE)
        surf.blit(fs_t, fs_t.get_rect(center=(W // 2, py + 150)))
        fl_t  = self.f_small.render("FINAL SCORE", True, C_DARK_GOLD)
        surf.blit(fl_t, fl_t.get_rect(center=(W // 2, py + 178)))

        # Breakdown
        fx_parts = []
        if self.fx_blur:   fx_parts.append(f"blur:{self.fx_blur}")
        if self.fx_wobble: fx_parts.append(f"wobble:{self.fx_wobble}")
        if self.fx_speed:  fx_parts.append(f"speed:{self.fx_speed}")
        if self.fx_delay:  fx_parts.append(f"delay:{self.fx_delay}")
        fx_str = "  ".join(fx_parts) if fx_parts else "sober"
        for j, line in enumerate([
            f"Base score:  {self.base_score}",
            f"Multiplier:  x{self.multiplier:.1f}",
            f"Survived:    {self.survive_time:.1f}s",
            f"Effects:     {fx_str}",
        ]):
            lt = self.f_small.render(line, True, C_WHITE)
            surf.blit(lt, lt.get_rect(center=(W // 2, py + 210 + j * 24)))

        # Rank
        rank, rcol = (
            ("LEGENDARY", C_GOLD)   if final > 1000 else
            ("RECKLESS",  C_RED)    if final > 500  else
            ("RISKY",     C_GOLD)   if final > 200  else
            ("CAUTIOUS",  C_BLUE)
        )
        rt = self.f_med.render(f"RANK:  {rank}", True, rcol)
        surf.blit(rt, rt.get_rect(center=(W // 2, py + 310)))

        # Restart
        flash = int(abs(math.sin(pygame.time.get_ticks() / 600)) * 200 + 55)
        rc_t  = self.f_med.render("PRESS ENTER / R TO RESTART", True, (flash, flash, flash // 2))
        surf.blit(rc_t, rc_t.get_rect(center=(W // 2, py + ph + 28)))


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
#  Standard Python guard: only runs when this file is executed directly,
#  not when imported as a module. Creates one DerbyDash instance and starts
#  the main loop, which runs until the window is closed.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    game = DerbyDash()
    game.run()