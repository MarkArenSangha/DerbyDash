"""
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
import sys
import math
import random

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
W, H = 900, 600
FPS  = 60
TITLE = "DERBY DASH"

# Colours
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

# Track / perspective
HORIZON_Y   = 200       # pixel row of vanishing point
GROUND_Y    = H         # pixel row at player's feet
LANE_COUNT  = 3
# At depth=0 (feet) the three lane centres in screen-X
LANE_FEET_X = [W * 0.18, W * 0.50, W * 0.82]

# Obstacle depth at which collision is checked
HIT_DEPTH_MIN = 0.00
HIT_DEPTH_MAX = 0.13

# ─────────────────────────────────────────────────────────────────────────────
#  DRINKS CATALOGUE
# ─────────────────────────────────────────────────────────────────────────────
DRINKS = [
    dict(name="WATER",   emoji="💧", symbol="~", mult=1.0, drunk=0, color=(126, 200, 227)),
    dict(name="BEER",    emoji="🍺", symbol="B", mult=1.2, drunk=1, color=(240, 165,   0)),
    dict(name="CIDER",   emoji="🍎", symbol="C", mult=1.5, drunk=2, color=(192,  57,  43)),
    dict(name="WHISKEY", emoji="🥃", symbol="W", mult=2.0, drunk=3, color=(139,  69,  19)),
    dict(name="VODKA",   emoji="🍸", symbol="V", mult=2.5, drunk=5, color=(160, 216, 239)),
]
MAX_DRINKS = 5

# ─────────────────────────────────────────────────────────────────────────────
#  OBSTACLE CATALOGUE  (h/w are fractions of lane-width at full scale)
# ─────────────────────────────────────────────────────────────────────────────
OBS_TYPES = [
    dict(label="FENCE",   color=(200, 168, 75), alt=(139, 105, 20),
         rel_w=0.90, rel_h=0.55, block_jump=False, block_duck=True),
    dict(label="HAY",     color=(232, 192, 96), alt=(160, 120, 48),
         rel_w=0.95, rel_h=0.50, block_jump=False, block_duck=True),
    dict(label="BARRIER", color=(231,  76, 60), alt=(192,  57, 43),
         rel_w=1.00, rel_h=0.35, block_jump=True,  block_duck=False),
    dict(label="HURDLE",  color=(93,  173, 226), alt=(41, 128, 185),
         rel_w=0.85, rel_h=0.60, block_jump=False, block_duck=True),
]

# ─────────────────────────────────────────────────────────────────────────────
#  PERSPECTIVE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def depth_to_y(depth: float) -> float:
    """depth 1.0 = horizon, 0.0 = player feet"""
    return HORIZON_Y + (GROUND_Y - HORIZON_Y) * (1.0 - depth)

def depth_to_scale(depth: float) -> float:
    return max(0.0, 1.0 - depth)

def lane_to_x(lane: int, depth: float) -> float:
    t = 1.0 - depth  # 0 at horizon, 1 at feet
    cx = W / 2
    foot_x = LANE_FEET_X[lane]
    return cx + (foot_x - cx) * t

def lane_pixel_width(depth: float) -> float:
    """How wide (px) a lane appears at this depth."""
    t = 1.0 - depth
    full_span = LANE_FEET_X[2] - LANE_FEET_X[0]  # px span across 3 lanes at feet
    return (full_span / LANE_COUNT) * t

# ─────────────────────────────────────────────────────────────────────────────
#  UTILITY — rounded-rect
# ─────────────────────────────────────────────────────────────────────────────
def draw_round_rect(surface, color, rect, radius=8, border=0, border_color=None):
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surface, border_color, rect, border, border_radius=radius)

# ─────────────────────────────────────────────────────────────────────────────
#  OBSTACLE  (dataclass-style)
# ─────────────────────────────────────────────────────────────────────────────
class Obstacle:
    def __init__(self, lane: int, otype: dict, spawn_depth: float = 1.0):
        self.lane       = lane
        self.depth      = spawn_depth
        self.label      = otype["label"]
        self.color      = otype["color"]
        self.alt        = otype["alt"]
        self.rel_w      = otype["rel_w"]
        self.rel_h      = otype["rel_h"]
        self.block_jump = otype["block_jump"]
        self.block_duck = otype["block_duck"]
        self.is_ghost   = False   # set True for passable triple-fence ghost lane

    def update(self, speed: float):
        self.depth -= speed

    def screen_rect(self) -> pygame.Rect:
        cx   = lane_to_x(self.lane, self.depth)
        base = depth_to_y(self.depth)
        lw   = lane_pixel_width(self.depth)
        w    = lw * self.rel_w
        h    = lw * self.rel_h
        return pygame.Rect(cx - w / 2, base - h, w, h)

    def draw(self, surf: pygame.Surface, drunk_level: int = 0):
        r = self.screen_rect()
        if r.width < 2 or r.height < 2:
            return
        is_ghost = getattr(self, "is_ghost", False)
        if is_ghost:
            # Draw ghost fence onto a temp SRCALPHA surface, then blit with reduced alpha.
            # Sober players see it clearly as faded; drunk players see almost opaque (hard to tell).
            # ghost_alpha: 80 when sober, rises to 210 when very drunk
            ghost_alpha = min(220, 80 + drunk_level * 14)
            tmp = pygame.Surface((r.width + 20, r.height + 20), pygame.SRCALPHA)
            tmp.fill((0, 0, 0, 0))
            r_local = pygame.Rect(10, 10, r.width, r.height)
            if self.label == "FENCE":
                self._draw_fence_on(tmp, r_local)
            # Set alpha of whole surface
            tmp.set_alpha(ghost_alpha)
            surf.blit(tmp, (r.x - 10, r.y - 10))
        else:
            if self.label == "FENCE":
                self._draw_fence(surf, r)
            elif self.label == "HAY":
                self._draw_hay(surf, r)
            elif self.label == "BARRIER":
                self._draw_barrier(surf, r)
            elif self.label == "HURDLE":
                self._draw_hurdle(surf, r)

    def _draw_fence(self, surf, r):
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
        """Same as _draw_fence but works on any surface (used for ghost alpha blit)."""
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
        # Drop shadow
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

    def _draw_barrier(self, surf, r):
        # Drop shadow
        sh = pygame.Surface((r.width + 8, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 110), (0, 0, r.width + 8, 10))
        surf.blit(sh, (r.x - 4, r.bottom + 1))
        # Draw onto a clipped subsurface to contain the stripes
        clip_surf = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
        clip_surf.fill(self.alt)
        stripe_w = max(5, r.width // 7)
        for i in range(-2, 10):
            sx = i * stripe_w * 2
            pts = [
                (sx,                 0),
                (sx + stripe_w,      0),
                (sx + stripe_w + r.height, r.height),
                (sx + r.height,      r.height),
            ]
            pygame.draw.polygon(clip_surf, (240, 220, 40), pts)
        # Bevel border
        pygame.draw.rect(clip_surf, self.alt, (0, 0, r.width, r.height), 3, border_radius=3)
        surf.blit(clip_surf, (r.x, r.y))
        # Bright top edge highlight
        hi = tuple(min(255, c + 60) for c in self.alt)
        pygame.draw.rect(surf, hi, (r.x, r.y, r.width, max(2, r.height // 5)), border_radius=3)
        pygame.draw.rect(surf, (0, 0, 0), r, 2, border_radius=3)

    def _draw_hurdle(self, surf, r):
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
#  SECURITY GUARD  (enemy)
# ─────────────────────────────────────────────────────────────────────────────
class Guard:
    def __init__(self, lane: int):
        self.lane         = lane
        self.depth        = 1.0
        self.anim         = 0       # walk cycle
        self.has_switched = False   # AI: only switch lane once ever

    def update(self, speed: float, player_lane: int):
        self.depth -= speed * 0.70
        self.anim  += 1
        # Switch toward player lane exactly once.
        # Random window: depth 0.65→0.50. Hard deadline: force switch at depth 0.45
        # so the guard ALWAYS finishes moving well before reaching the hit zone (0.13).
        if not self.has_switched:
            if self.depth < 0.65 and random.random() < 0.025:
                self.lane         = player_lane
                self.has_switched = True
            elif self.depth <= 0.45:
                self.lane         = player_lane
                self.has_switched = True

    def draw(self, surf: pygame.Surface):
        cx   = lane_to_x(self.lane, self.depth)
        base = depth_to_y(self.depth)
        sc   = depth_to_scale(self.depth)
        if sc < 0.04:
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
# ─────────────────────────────────────────────────────────────────────────────
class DerbyDash:
    # ── states ────────────────────────────────────────────────────────────────
    STATE_BAR      = "bar"
    STATE_RACE     = "race"
    STATE_GAMEOVER = "gameover"

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption(TITLE)
        self.clock  = pygame.time.Clock()

        # Fonts
        self.f_huge   = pygame.font.SysFont("monospace", 64, bold=True)
        self.f_large  = pygame.font.SysFont("monospace", 32, bold=True)
        self.f_med    = pygame.font.SysFont("monospace", 18, bold=True)
        self.f_small  = pygame.font.SysFont("monospace", 13)
        self.f_tiny   = pygame.font.SysFont("monospace", 11)

        self._reset_bar()
        self.state = self.STATE_BAR

    # ── reset helpers ─────────────────────────────────────────────────────────
    def _reset_bar(self):
        self.drink_history = []   # list of drink dicts added
        self.drunk_level   = 0
        self.multiplier    = 1.0
        self.selected_drink = 0

    def _reset_race(self):
        self.obstacles     = []
        self.guards        = []
        self.player_lane   = 1
        self.player_y      = 0.0   # px offset (negative = in air)
        self.is_jumping    = False
        self.is_ducking    = False
        self.jump_vel      = 0.0
        self.base_score    = 0
        self.survive_time  = 0.0
        self.race_frame    = 0
        self.game_speed    = 0.010
        self.spawn_timer   = 0
        self.spawn_interval = 80
        self.bg_offset     = 0.0
        # Drunk FX
        self.input_queue   = []    # (frame_to_fire, action)
        self.sway_angle    = 0.0
        self.distort_phase = 0.0
        self.stumble_timer = 0
        self.stumble_dx    = 0.0
        self.drunk_flash   = 0     # countdown for flash overlay

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            self._handle_events()
            if self.state == self.STATE_BAR:
                self._update_bar()
                self._draw_bar()
            elif self.state == self.STATE_RACE:
                self._update_race()
                self._draw_race()
            elif self.state == self.STATE_GAMEOVER:
                self._draw_gameover()
            pygame.display.flip()

    # ─────────────────────────────────────────────────────────────────────────
    #  EVENT HANDLING
    # ─────────────────────────────────────────────────────────────────────────
    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN:
                if self.state == self.STATE_BAR:
                    self._bar_keydown(event.key)
                elif self.state == self.STATE_RACE:
                    self._race_keydown(event.key)
                elif self.state == self.STATE_GAMEOVER:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_r):
                        self._reset_bar()
                        self.state = self.STATE_BAR

            if event.type == pygame.KEYUP:
                if self.state == self.STATE_RACE:
                    if event.key == pygame.K_DOWN:
                        self.is_ducking = False

    # ─────────────────────────────────────────────────────────────────────────
    #  BAR PHASE
    # ─────────────────────────────────────────────────────────────────────────
    def _bar_keydown(self, key):
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
        if len(self.drink_history) >= MAX_DRINKS:
            return
        d = DRINKS[self.selected_drink]
        self.drink_history.append(d)
        self.drunk_level += d["drunk"]
        self.multiplier  *= d["mult"]

    def _remove_drink(self):
        if not self.drink_history:
            return
        d = self.drink_history.pop()
        self.drunk_level -= d["drunk"]
        self.multiplier  /= d["mult"]
        self.drunk_level  = max(0, self.drunk_level)
        self.multiplier   = max(1.0, self.multiplier)

    def _start_race(self):
        self._reset_race()
        self.state = self.STATE_RACE

    def _update_bar(self):
        pass  # nothing needs updating every frame in bar state

    def _draw_bar(self):
        surf = self.screen
        t    = pygame.time.get_ticks() / 1000.0
        max_drunk = 15

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
            # Mirror reflection
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

        # Stools
        for sx in (W//2 - 130, W//2 + 130):
            pygame.draw.ellipse(surf, (68, 38, 8),  (sx-30, counter_y-6, 60, 16))
            pygame.draw.ellipse(surf, (88, 52, 14), (sx-28, counter_y-8, 56, 12))
            pygame.draw.line(surf, (78, 46, 10), (sx, counter_y+10), (sx, H-22), 6)
            pygame.draw.line(surf, (78, 46, 10), (sx-22, H-42), (sx+22, H-42), 4)

        # Glasses on counter
        for gx, gcol in ((W//2-65, (240,195,55,170)), (W//2+65, (175,215,255,155))):
            gl = pygame.Surface((24, 32), pygame.SRCALPHA)
            pygame.draw.rect(gl, (195,215,235,75),  (1,  0, 22, 30), border_radius=3)
            pygame.draw.rect(gl, gcol,               (2,  7, 20, 20), border_radius=2)
            pygame.draw.rect(gl, (255,255,255,115),  (3, 9,  5,  16))
            surf.blit(gl, (gx-12, counter_y-26))

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

        # Arms wiping bar
        wipe = int(math.sin(t * 1.4) * 28)
        pygame.draw.line(surf, (228,222,212), (bm_x-24, bm_ground-65), (bm_x-52+wipe, bm_ground-18), 11)
        pygame.draw.line(surf, (228,222,212), (bm_x+24, bm_ground-65), (bm_x+22+wipe, bm_ground-18), 11)
        # Cloth
        pygame.draw.ellipse(surf, (195,192,178), (bm_x+14+wipe, bm_ground-24, 20, 10))

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
            sym = self.f_large.render(d2["symbol"], True, d2["color"])
            surf.blit(sym, sym.get_rect(center=(cx+card_w//2, counter_y-card_h+24)))
            nm2 = self.f_small.render(d2["name"],  True, d2["color"])
            surf.blit(nm2, nm2.get_rect(center=(cx+card_w//2, counter_y-card_h+50)))
            ms2 = self.f_tiny.render(f"x{d2['mult']:.1f}  +{d2['drunk']}drunk", True, (175,138,58))
            surf.blit(ms2, ms2.get_rect(center=(cx+card_w//2, counter_y-card_h+68)))
            if sel:
                ar = self.f_tiny.render("SELECTED", True, d2["color"])
                surf.blit(ar, ar.get_rect(center=(cx+card_w//2, counter_y-card_h+82)))

        # ── ORDER HISTORY + DRUNK METER ───────────────────────────────────────
        hist_lbl = self.f_tiny.render(
            f"ORDERED: {len(self.drink_history)}/{MAX_DRINKS}    "
            f"MULT: x{self.multiplier:.2f}    DRUNK: {self.drunk_level}",
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
        delay_frames = self.drunk_level * 5
        if key == pygame.K_LEFT:
            self.input_queue.append((self.race_frame + delay_frames, "left"))
        elif key == pygame.K_RIGHT:
            self.input_queue.append((self.race_frame + delay_frames, "right"))
        elif key == pygame.K_UP:
            self.input_queue.append((self.race_frame + delay_frames, "jump"))
        elif key == pygame.K_DOWN:
            self.is_ducking = True  # duck is instant (hold key), no delay

    def _process_input_queue(self):
        remaining = []
        for (fire_at, action) in self.input_queue:
            if self.race_frame >= fire_at:
                if action == "left":
                    self.player_lane = max(0, self.player_lane - 1)
                elif action == "right":
                    self.player_lane = min(2, self.player_lane + 1)
                elif action == "jump" and not self.is_jumping:
                    self.is_jumping = True
                    self.jump_vel   = -16.0
            else:
                remaining.append((fire_at, action))
        self.input_queue = remaining

    def _update_race(self):
        self.race_frame  += 1
        self.survive_time = self.race_frame / FPS
        self.base_score   = int(self.survive_time * 10)

        # Speed / difficulty ramp
        self.game_speed    = 0.010 + self.survive_time * 0.00013
        self.spawn_interval = max(32, 80 - self.survive_time * 1.0)

        # Spawn — sober = obstacles spawn further away (more warning time)
        # drunk_level=0 -> spawn_depth=1.0 (full horizon distance)
        # drunk_level=10 -> spawn_depth=0.70 (much closer, less warning)
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            spawn_depth = max(0.70, 1.0 - self.drunk_level * 0.030)
            # 15% chance to spawn a triple-fence obstacle set instead of normal
            if random.random() < 0.15:
                ghost_lane = random.randint(0, 2)
                for lane in range(3):
                    obs = Obstacle(lane, OBS_TYPES[0], spawn_depth=spawn_depth)
                    obs.is_ghost = (lane == ghost_lane)
                    self.obstacles.append(obs)
            else:
                otype = random.choice(OBS_TYPES)
                lane  = random.randint(0, 2)
                obs   = Obstacle(lane, otype, spawn_depth=spawn_depth)
                obs.is_ghost = False
                self.obstacles.append(obs)
            if random.random() < 0.22:
                g = Guard(random.randint(0, 2))
                self.guards.append(g)

        # Jump physics
        if self.is_jumping:
            self.jump_vel   += 0.9
            self.player_y   += self.jump_vel
            if self.player_y >= 0:
                self.player_y  = 0
                self.is_jumping = False
                self.jump_vel   = 0.0

        # Drunk effects
        self.sway_angle    = math.sin(self.race_frame * 0.04) * self.drunk_level * 0.018
        self.distort_phase += 0.05 + self.drunk_level * 0.01
        if self.drunk_level >= 3:
            self.stumble_timer -= 1
            if self.stumble_timer <= 0:
                self.stumble_timer = random.randint(55, 130)
                self.stumble_dx    = (random.random() - 0.5) * 26 * self.drunk_level \
                                     if random.random() < 0.4 else 0.0

        self._process_input_queue()

        # Move objects
        for obs in self.obstacles:
            obs.update(self.game_speed)
        self.obstacles = [o for o in self.obstacles if o.depth > -0.08]

        for g in self.guards:
            g.update(self.game_speed, self.player_lane)
        self.guards = [g for g in self.guards if g.depth > -0.08]

        # Collision detection — hit zone is depth 0.0–0.13
        for obs in self.obstacles:
            if obs.lane != self.player_lane:
                continue
            if getattr(obs, "is_ghost", False):
                continue   # ghost fence is passable
            if not (HIT_DEPTH_MIN <= obs.depth <= HIT_DEPTH_MAX):
                continue
            clear_jump = self.is_jumping and self.player_y < -28 and not obs.block_jump
            clear_duck = self.is_ducking and obs.block_duck
            if not clear_jump and not clear_duck:
                self.state = self.STATE_GAMEOVER
                return

        for g in self.guards:
            if g.lane == self.player_lane and HIT_DEPTH_MIN <= g.depth <= HIT_DEPTH_MAX:
                self.state = self.STATE_GAMEOVER
                return

        self.bg_offset += self.game_speed * 60

    def _draw_race(self):
        surf = self.screen

        # ── Camera shake / sway ───────────────────────────────────────────────
        sway_x = math.sin(self.race_frame * 0.055) * self.drunk_level * 5 + self.stumble_dx * 0.3
        # We draw everything onto a temp surface then rotate/offset it
        scene = pygame.Surface((W, H))

        self._draw_track_bg(scene)

        # Sort obstacles + guards back-to-front (high depth = far = draw first)
        all_objs = [(obs.depth, obs, "obs") for obs in self.obstacles] +                    [(g.depth,   g,   "grd") for g   in self.guards]
        all_objs.sort(key=lambda x: -x[0])
        for _, obj, kind in all_objs:
            if kind == "obs":
                obj.draw(scene, drunk_level=self.drunk_level)
            else:
                obj.draw(scene)

        self._draw_player(scene)

        # Drunk overlays
        if self.drunk_level >= 2:
            vig = pygame.Surface((W, H), pygame.SRCALPHA)
            alpha = min(180, self.drunk_level * 18)
            pygame.draw.circle(vig, (180, 0, 0, 0), (W // 2, H // 2), W // 2)
            # radial vignette
            for radius in range(W // 2, W // 2 - 80, -8):
                a = max(0, int((1 - radius / (W / 2)) * alpha * 2))
                pygame.draw.circle(vig, (0, 0, 0, a), (W // 2, H // 2), radius, 8)
            scene.blit(vig, (0, 0))

        if self.drunk_level >= 4:
            flash_alpha = int(abs(math.sin(self.distort_phase)) * (self.drunk_level - 3) * 20)
            flash = pygame.Surface((W, H), pygame.SRCALPHA)
            flash.fill((0, 180, 0, flash_alpha))
            scene.blit(flash, (0, 0))

        # Apply sway rotation to scene
        angle_deg = math.degrees(self.sway_angle)
        rotated   = pygame.transform.rotate(scene, angle_deg)
        rx = W // 2 - rotated.get_width()  // 2 + int(sway_x)
        ry = H // 2 - rotated.get_height() // 2
        surf.blit(rotated, (rx, ry))

        self._draw_hud(surf)

    def _draw_track_bg(self, surf):
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
        for lx in (65, W - 65):
            cone = pygame.Surface((260, HORIZON_Y + 60), pygame.SRCALPHA)
            tip_x = 130
            pygame.draw.polygon(cone, (255, 240, 180, 18),
                                 [(tip_x, 0), (0, HORIZON_Y + 60), (260, HORIZON_Y + 60)])
            surf.blit(cone, (lx - 130, 0))

        # ── 3. STADIUM STANDS — solid two-tier blocks ────────────────────────
        stand_top_y = 10
        stand_bot_y = HORIZON_Y - 2
        stand_h     = stand_bot_y - stand_top_y
        pygame.draw.rect(surf, (28, 22, 40), (0, stand_top_y, W // 2 + 30, stand_h))
        pygame.draw.rect(surf, (24, 18, 36), (W // 2 - 30, stand_top_y, W // 2 + 30, stand_h))
        for tier in range(8):
            ty  = stand_top_y + int(stand_h * tier / 8)
            col = (35 + tier * 2, 28 + tier * 2, 50 + tier * 2)
            pygame.draw.line(surf, col, (0, ty), (W, ty), 1)

        # Crowd dots
        crowd_cols = [(220,50,50),(50,180,220),(240,200,40),
                      (180,80,220),(60,220,100),(255,255,255),(240,120,40)]
        rng = random.Random(42)
        for _ in range(420):
            fx = rng.randint(0, W)
            fy = rng.randint(stand_top_y + 6, stand_bot_y - 4)
            fc = crowd_cols[rng.randint(0, len(crowd_cols) - 1)]
            pygame.draw.circle(surf, fc, (fx, fy), rng.randint(1, 3))

        # ── 4. FLOODLIGHT PYLONS ─────────────────────────────────────────────
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

        # ── 5. ADVERTISING BOARDS (scrolling) ────────────────────────────────
        board_h = 20
        board_y = HORIZON_Y - board_h - 2
        board_colors = [(200,30,30),(30,100,200),(220,180,0),(30,160,30),(200,80,200),(240,120,0)]
        board_texts  = ["DERBY DASH","BET NOW","GOLD CUP","RACE DAY","SPONSOR","VIP ZONE"]
        board_w = 110
        for bi in range(8):
            bx  = int((bi * 130 + self.bg_offset * 0.5) % (W + 130)) - 65
            col = board_colors[bi % len(board_colors)]
            pygame.draw.rect(surf, col, (bx, board_y, board_w, board_h))
            pygame.draw.rect(surf, (255, 255, 255), (bx, board_y, board_w, board_h), 1)
            txt = self.f_tiny.render(board_texts[bi % len(board_texts)], True, (255, 255, 255))
            surf.blit(txt, txt.get_rect(center=(bx + board_w // 2, board_y + board_h // 2)))

        # ── 6. GROUND — arena dirt gradient ──────────────────────────────────
        dirt_top = (110, 88, 55)
        dirt_bot = (75,  58, 32)
        for i in range(HORIZON_Y, H):
            t   = (i - HORIZON_Y) / (H - HORIZON_Y)
            col = tuple(int(dirt_top[c] + (dirt_bot[c] - dirt_top[c]) * t) for c in range(3))
            pygame.draw.line(surf, col, (0, i), (W, i))

        # ── 7. TRACK SURFACE — scrolling stripes ─────────────────────────────
        edge_off = 0.55
        def track_edges(depth):
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

        # ── 8. CONCRETE ARENA WALLS ───────────────────────────────────────────
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

        # ── 9. RED/WHITE KERBING ──────────────────────────────────────────────
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

        # ── 10. LANE LINES ────────────────────────────────────────────────────
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
        pygame.draw.line(surf, (50, 38, 22), (0, HORIZON_Y), (W, HORIZON_Y), 2)

    def _draw_player(self, surf):
        """Front-facing horse + jockey viewed from behind/below."""
        px     = int(lane_to_x(self.player_lane, 0.0) + self.stumble_dx)
        ground = H - 10
        jy     = int(self.player_y)   # negative = in air
        t      = self.bg_offset
        bob    = int(math.sin(t * 0.55) * 4)
        base_y = ground + jy + bob

        # ── SHADOW ────────────────────────────────────────────────────────────
        shadow_scale = max(0.25, 1.0 - abs(jy) / 110)
        sw = int(120 * shadow_scale)
        sh_s = pygame.Surface((sw, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(sh_s, (0, 0, 0, int(75 * shadow_scale)), (0, 0, sw, 14))
        surf.blit(sh_s, (px - sw // 2, ground - 4))

        horse_col = (62, 38, 16)
        horse_hi  = (92, 58, 26)
        hoof_col  = (28, 18, 6)
        leg_col   = (50, 30, 10)
        gait      = t * 0.55

        # ── REAR LEGS (wide stance, front-on) ────────────────────────────────
        for side, sign in ((-1, -1), (1, 1)):
            kick = int(math.sin(gait + (0 if side == -1 else math.pi)) * 14)
            lx   = px + sign * 28
            # upper leg segment
            knee_x = lx + sign * 8
            knee_y = base_y - 28
            pygame.draw.line(surf, leg_col, (lx, base_y - 52), (knee_x, knee_y), 10)
            # lower leg
            foot_x = lx + sign * 14 + kick
            pygame.draw.line(surf, leg_col, (knee_x, knee_y), (foot_x, base_y - 4), 8)
            # hoof
            pygame.draw.ellipse(surf, hoof_col,
                                (foot_x - 10, base_y - 8, 20, 10))

        # ── HORSE BODY (front-on torso — wider than tall, foreshortened) ─────
        body_w = 90
        body_h = 52
        body_y = base_y - 90
        # Main ellipse body
        pygame.draw.ellipse(surf, horse_col, (px - body_w // 2, body_y, body_w, body_h))
        # Chest highlight
        pygame.draw.ellipse(surf, horse_hi,
                            (px - body_w // 4, body_y + 6, body_w // 2, body_h // 3))
        # Belly lower curve
        pygame.draw.ellipse(surf, (48, 30, 12),
                            (px - body_w // 2 + 4, body_y + body_h - 14,
                             body_w - 8, 18))

        # ── FRONT LEGS (slightly in front of body, front-on) ─────────────────
        for side, sign in ((-1, -1), (1, 1)):
            kick = int(math.sin(gait + math.pi * 0.5 + (0 if side == -1 else math.pi)) * 10)
            lx   = px + sign * 18
            knee_x = lx + sign * 4
            knee_y = base_y - 20
            pygame.draw.line(surf, leg_col, (lx, body_y + body_h), (knee_x, knee_y), 9)
            foot_x = lx + sign * 8 + kick
            pygame.draw.line(surf, leg_col, (knee_x, knee_y), (foot_x, base_y - 4), 7)
            pygame.draw.ellipse(surf, hoof_col, (foot_x - 9, base_y - 8, 18, 9))

        # ── NECK (shorter, pointing upward from centre of chest) ─────────────
        neck_w = 28
        neck_h = 38
        neck_y = body_y - neck_h + 8
        pygame.draw.ellipse(surf, horse_col, (px - neck_w // 2, neck_y, neck_w, neck_h + 10))
        pygame.draw.ellipse(surf, horse_hi,
                            (px - neck_w // 4, neck_y + 4, neck_w // 2, neck_h // 3))

        # ── HEAD (front-on: roughly round with wide nostrils) ─────────────────
        head_y = neck_y - 32
        head_w = 38
        head_h = 46
        pygame.draw.ellipse(surf, horse_col, (px - head_w // 2, head_y, head_w, head_h))
        # Blaze (white stripe down centre of face)
        pygame.draw.ellipse(surf, (220, 215, 200),
                            (px - 5, head_y + 6, 10, head_h - 14))
        # Eyes (front-on: both visible, one each side)
        for ex in (-14, 14):
            pygame.draw.circle(surf, (20, 12, 4),  (px + ex, head_y + 14), 5)
            pygame.draw.circle(surf, (255, 240, 180), (px + ex + 1, head_y + 13), 2)
        # Nostrils (large, front-on)
        for nx in (-9, 9):
            pygame.draw.ellipse(surf, (38, 18, 6),
                                (px + nx - 5, head_y + head_h - 16, 10, 7))
        # Bridle across nose
        pygame.draw.line(surf, (160, 120, 50),
                         (px - head_w // 2 + 2, head_y + head_h - 18),
                         (px + head_w // 2 - 2, head_y + head_h - 18), 3)
        # Crown piece / browband
        pygame.draw.line(surf, (160, 120, 50),
                         (px - head_w // 2 + 4, head_y + 10),
                         (px + head_w // 2 - 4, head_y + 10), 2)
        # Ears (two small triangles)
        for ex, ep in ((-10, -1), (10, 1)):
            pygame.draw.polygon(surf, horse_col, [
                (px + ex - 4, head_y + 4),
                (px + ex + 4, head_y + 4),
                (px + ex + ep, head_y - 10),
            ])
        # Mane (hair tuft between ears, flutter)
        mane_wave = int(math.sin(t * 0.4) * 3)
        for mi in range(5):
            mx2 = px - 6 + mi * 3
            pygame.draw.line(surf, (25, 14, 4),
                             (mx2, head_y + 2),
                             (mx2 + mane_wave, head_y - 8 - mi * 2), 2)

        # ── JOCKEY (sits above the horse, leans forward over neck) ───────────
        if self.is_ducking:
            # Tucked right down — just a helmet poking above the neck
            helm_y = neck_y - 14
            pygame.draw.ellipse(surf, (180, 40, 40), (px - 14, helm_y - 10, 28, 18))
            pygame.draw.rect(surf, (150, 28, 28), (px - 16, helm_y + 6, 32, 5), border_radius=2)
        else:
            jock_y = neck_y - 4   # jockey seat level (just above horse shoulders)

            # Seat / lower body astride the horse
            pygame.draw.ellipse(surf, (44, 62, 80), (px - 20, jock_y - 10, 40, 16))

            # Torso — angled forward over neck
            arm_bob = int(math.sin(t * 0.55) * 3)
            tor_x   = px
            tor_bot = jock_y - 4
            tor_top = jock_y - 32 + arm_bob
            # Draw torso as a thick line (front-on, so it's narrow)
            pygame.draw.line(surf, (44, 62, 80), (tor_x, tor_bot), (tor_x, tor_top), 16)
            # Silk stripes across torso (horizontal bands)
            for si, sc_col in enumerate([(220, 50, 50), (240, 240, 60), (220, 50, 50)]):
                sy = tor_bot - 6 - si * 8
                pygame.draw.line(surf, sc_col, (tor_x - 8, sy), (tor_x + 8, sy), 4)

            # Arms out each side gripping reins
            arm_y  = tor_top + 8 + arm_bob
            for side, sign in ((-1, -1), (1, 1)):
                ax = tor_x + sign * 24
                pygame.draw.line(surf, (44, 62, 80), (tor_x, arm_y), (ax, arm_y + 6), 6)
                # Reins dropping forward from hands
                pygame.draw.line(surf, (160, 120, 50),
                                 (ax, arm_y + 6), (ax + sign * 4, head_y + head_h - 16), 2)

            # Head (front-on: small oval above torso)
            head_r = 11
            hx, hy = tor_x, tor_top - head_r + 2
            pygame.draw.circle(surf, (210, 165, 120), (hx, hy), head_r)
            # Helmet
            pygame.draw.ellipse(surf, (180, 40, 40),
                                (hx - head_r - 1, hy - head_r - 1, head_r * 2 + 2, head_r + 4))
            pygame.draw.rect(surf, (150, 28, 28),
                             (hx - head_r - 3, hy + 2, head_r * 2 + 6, 4), border_radius=2)
            # Goggles (two circles side by side, front-on)
            pygame.draw.ellipse(surf, (60, 130, 200), (hx - 11, hy - 4, 9, 6))
            pygame.draw.ellipse(surf, (60, 130, 200), (hx + 2,  hy - 4, 9, 6))

        # ── Lane indicators ──────────────────────────────────────────────────
        for i in range(3):
            dot_x  = int(lane_to_x(i, 0.0))
            active = (i == self.player_lane)
            pygame.draw.circle(surf, (0, 0, 0),   (dot_x, H - 13), 7)
            pygame.draw.circle(surf, C_WHITE if active else C_DARK_GOLD, (dot_x, H - 13), 5)
            if active:
                pygame.draw.circle(surf, (255, 255, 255), (dot_x, H - 13), 3)

    def _draw_hud(self, surf):
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
        mult_col = (255, 120, 40) if self.multiplier >= 5 else \
                   C_GOLD         if self.multiplier >= 2 else C_WHITE
        mt = self.f_large.render(f"x{self.multiplier:.1f}", True, mult_col)
        surf.blit(mt, mt.get_rect(center=(W // 2, 24)))

        # Time (right)
        tt = self.f_large.render(f"{self.survive_time:.1f}s", True, C_WHITE)
        surf.blit(tt, (W - tt.get_width() - 16, 8))

        # ── Drunk level indicator (bottom-left) ───────────────────────────────
        if self.drunk_level > 0:
            dl_bg = pygame.Surface((220, 32), pygame.SRCALPHA)
            dl_bg.fill((0, 0, 0, 120))
            surf.blit(dl_bg, (0, H - 32))

            label = ("WRECKED"   if self.drunk_level >= 8 else
                     "VERY DRUNK" if self.drunk_level >= 4 else
                     "TIPSY")
            dcol = C_RED if self.drunk_level >= 4 else C_GOLD
            dt = self.f_small.render(f"* {label}", True, dcol)
            surf.blit(dt, (10, H - 26))

        # Input delay warning
        if self.input_queue:
            wt = self.f_tiny.render(f"  {len(self.input_queue)} input(s) queued...", True, (255, 140, 40))
            surf.blit(wt, (10, H - 44))

        # ── Jump / duck state (bottom-centre) ────────────────────────────────
        if self.is_jumping:
            jt = self.f_med.render("[ JUMP ]", True, (100, 180, 255))
            surf.blit(jt, jt.get_rect(center=(W // 2, H - 24)))
        elif self.is_ducking:
            dt2 = self.f_med.render("[ DUCK ]", True, (80, 220, 120))
            surf.blit(dt2, dt2.get_rect(center=(W // 2, H - 24)))

        # Controls reminder fading over first 5 seconds
        if self.survive_time < 5:
            alpha = int(220 * min(1.0, (5 - self.survive_time) / 2))
            ct_bg = pygame.Surface((W, 22), pygame.SRCALPHA)
            ct_bg.fill((0, 0, 0, alpha // 2))
            surf.blit(ct_bg, (0, H - 22))
            ct    = self.f_tiny.render("LEFT / RIGHT — change lane     UP — jump     DOWN — duck", True,
                                       (int(C_DARK_GOLD[0] * alpha / 220),
                                        int(C_DARK_GOLD[1] * alpha / 220),
                                        int(C_DARK_GOLD[2] * alpha / 220)))
            surf.blit(ct, ct.get_rect(center=(W // 2, H - 11)))

    # ─────────────────────────────────────────────────────────────────────────
    #  GAME OVER
    # ─────────────────────────────────────────────────────────────────────────
    def _draw_gameover(self):
        surf = self.screen
        surf.fill((8, 3, 0))

        # Scanline texture
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
        for j, line in enumerate([
            f"Base score:  {self.base_score}",
            f"Multiplier:  x{self.multiplier:.1f}",
            f"Survived:    {self.survive_time:.1f}s",
            f"Drunk level: {self.drunk_level}",
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
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    game = DerbyDash()
    game.run()
