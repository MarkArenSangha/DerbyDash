# Download
# download pygame from pip on terminal
# Import file
import pygame
# Game begin

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
    dict(name="BEER",    emoji="🍺", symbol="B", mult=1.5, drunk=1, color=(240, 165,   0)),
    dict(name="CIDER",   emoji="🍎", symbol="C", mult=2.0, drunk=2, color=(192,  57,  43)),
    dict(name="WHISKEY", emoji="🥃", symbol="W", mult=3.0, drunk=3, color=(139,  69,  19)),
    dict(name="VODKA",   emoji="🍸", symbol="V", mult=5.0, drunk=5, color=(160, 216, 239)),
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
    def __init__(self, lane: int, otype: dict):
        self.lane      = lane
        self.depth     = 1.0
        self.label     = otype["label"]
        self.color     = otype["color"]
        self.alt       = otype["alt"]
        self.rel_w     = otype["rel_w"]
        self.rel_h     = otype["rel_h"]
        self.block_jump = otype["block_jump"]
        self.block_duck = otype["block_duck"]

    def update(self, speed: float):
        self.depth -= speed

    def screen_rect(self) -> pygame.Rect:
        cx   = lane_to_x(self.lane, self.depth)
        base = depth_to_y(self.depth)
        lw   = lane_pixel_width(self.depth)
        w    = lw * self.rel_w
        h    = lw * self.rel_h
        return pygame.Rect(cx - w / 2, base - h, w, h)

    def draw(self, surf: pygame.Surface):
        r = self.screen_rect()
        if r.width < 2 or r.height < 2:
            return
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
        self.lane  = lane
        self.depth = 1.0
        self.anim  = 0  # walk cycle

    def update(self, speed: float, player_lane: int):
        self.depth -= speed * 0.70
        self.anim  += 1
        # Occasionally drift toward player lane (AI)
        if random.random() < 0.007:
            self.lane = player_lane

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
        surf.fill(C_BG)

        # Background wood texture lines
        for i in range(0, H, 18):
            pygame.draw.line(surf, (18, 9, 0), (0, i), (W, i))

        # Title bar
        pygame.draw.rect(surf, (30, 15, 0), (0, 0, W, 56))
        pygame.draw.line(surf, C_DARK_GOLD, (0, 56), (W, 56), 2)
        title = self.f_large.render("🏇  DERBY DASH  —  THE BAR  🍺", True, C_WHITE)
        surf.blit(title, title.get_rect(center=(W // 2, 28)))

        # Stats row
        stats = self.f_med.render(
            f"DRINKS: {len(self.drink_history)}/{MAX_DRINKS}     "
            f"MULTIPLIER: x{self.multiplier:.1f}     "
            f"DRUNK LEVEL: {self.drunk_level}",
            True, C_GOLD)
        surf.blit(stats, stats.get_rect(center=(W // 2, 76)))

        # Drunk meter
        max_drunk = 15
        meter_w, meter_h = 340, 14
        mx = W // 2 - meter_w // 2
        my = 92
        pygame.draw.rect(surf, (30, 15, 0), (mx, my, meter_w, meter_h))
        frac = min(self.drunk_level / max_drunk, 1.0)
        bar_color = C_GREEN if frac < 0.4 else (C_GOLD if frac < 0.70 else C_RED)
        pygame.draw.rect(surf, bar_color, (mx, my, int(meter_w * frac), meter_h))
        pygame.draw.rect(surf, C_DARK_GOLD, (mx, my, meter_w, meter_h), 1)
        label_l = self.f_tiny.render("SOBER", True, C_DARK_GOLD)
        label_r = self.f_tiny.render("WRECKED", True, C_DARK_GOLD)
        surf.blit(label_l, (mx, my + meter_h + 3))
        surf.blit(label_r, (mx + meter_w - label_r.get_width(), my + meter_h + 3))

        # ── Drink cards ───────────────────────────────────────────────────────
        card_w, card_h = 140, 130
        gap = 12
        total_w = len(DRINKS) * card_w + (len(DRINKS) - 1) * gap
        start_x = W // 2 - total_w // 2
        card_y  = 128

        for i, d in enumerate(DRINKS):
            cx   = start_x + i * (card_w + gap)
            sel  = (i == self.selected_drink)
            border_col = d["color"] if sel else (60, 30, 0)
            bg_col     = (36, 18, 0) if sel else (20, 10, 0)
            draw_round_rect(surf, bg_col, (cx, card_y, card_w, card_h), 8,
                            border=2 if sel else 1, border_color=border_col)

            # Glow behind selected card
            if sel:
                glow_surf = pygame.Surface((card_w + 20, card_h + 20), pygame.SRCALPHA)
                glow_col  = d["color"] + (40,)
                pygame.draw.rect(glow_surf, glow_col, (0, 0, card_w + 20, card_h + 20), border_radius=14)
                surf.blit(glow_surf, (cx - 10, card_y - 10))
                draw_round_rect(surf, bg_col, (cx, card_y, card_w, card_h), 8,
                                border=2, border_color=border_col)

            # Drink symbol (large letter since emoji rendering varies)
            sym_surf = self.f_large.render(d["symbol"], True, d["color"])
            surf.blit(sym_surf, sym_surf.get_rect(center=(cx + card_w // 2, card_y + 34)))

            name_surf = self.f_small.render(d["name"], True, d["color"])
            surf.blit(name_surf, name_surf.get_rect(center=(cx + card_w // 2, card_y + 62)))

            mult_surf = self.f_tiny.render(f"x{d['mult']:.1f} MULT", True, C_WHITE)
            surf.blit(mult_surf, mult_surf.get_rect(center=(cx + card_w // 2, card_y + 82)))

            drunk_surf = self.f_tiny.render(f"+{d['drunk']} DRUNK", True, (180, 140, 60))
            surf.blit(drunk_surf, drunk_surf.get_rect(center=(cx + card_w // 2, card_y + 98)))

            # "SELECTED" arrow
            if sel:
                arr = self.f_tiny.render("▲ SELECTED", True, d["color"])
                surf.blit(arr, arr.get_rect(center=(cx + card_w // 2, card_y + 118)))

        # ── Added drinks history dots ─────────────────────────────────────────
        dot_y = card_y + card_h + 22
        for i in range(MAX_DRINKS):
            dot_x = W // 2 - (MAX_DRINKS * 22) // 2 + i * 22 + 11
            pygame.draw.circle(surf, C_DARK_GOLD, (dot_x, dot_y), 7)
            if i < len(self.drink_history):
                pygame.draw.circle(surf, self.drink_history[i]["color"], (dot_x, dot_y), 6)

        # ── Info panel (selected drink details) ──────────────────────────────
        panel_x, panel_y, panel_w, panel_h = 28, 130, 180, 200
        draw_round_rect(surf, C_PANEL, (panel_x, panel_y, panel_w, panel_h), 8,
                        border=1, border_color=(60, 30, 0))
        d = DRINKS[self.selected_drink]
        ph = self.f_med.render("SELECTED", True, C_DARK_GOLD)
        surf.blit(ph, ph.get_rect(center=(panel_x + panel_w // 2, panel_y + 18)))
        sym = self.f_huge.render(d["symbol"], True, d["color"])
        surf.blit(sym, sym.get_rect(center=(panel_x + panel_w // 2, panel_y + 70)))
        nm  = self.f_med.render(d["name"], True, d["color"])
        surf.blit(nm, nm.get_rect(center=(panel_x + panel_w // 2, panel_y + 108)))
        for j, line in enumerate([
                f"Multiplier: x{d['mult']:.1f}",
                f"Drunk add:  +{d['drunk']}",
        ]):
            t = self.f_tiny.render(line, True, C_WHITE)
            surf.blit(t, t.get_rect(center=(panel_x + panel_w // 2, panel_y + 132 + j * 16)))

        # Effects warning
        effects = []
        if d["drunk"] >= 1: effects.append("Input delay")
        if d["drunk"] >= 2: effects.append("Camera sway")
        if d["drunk"] >= 3: effects.append("Stumbles")
        if d["drunk"] >= 5: effects.append("Distortion")
        for j, ef in enumerate(effects):
            t = self.f_tiny.render(f"! {ef}", True, C_RED)
            surf.blit(t, t.get_rect(center=(panel_x + panel_w // 2, panel_y + 164 + j * 14)))

        # ── Current build panel ───────────────────────────────────────────────
        bp_x, bp_y, bp_w, bp_h = W - 28 - 180, 130, 180, 200
        draw_round_rect(surf, C_PANEL, (bp_x, bp_y, bp_w, bp_h), 8,
                        border=1, border_color=(60, 30, 0))
        bh_t = self.f_med.render("YOUR BUILD", True, C_DARK_GOLD)
        surf.blit(bh_t, bh_t.get_rect(center=(bp_x + bp_w // 2, bp_y + 18)))
        m_t = self.f_large.render(f"x{self.multiplier:.1f}", True, C_WHITE)
        surf.blit(m_t, m_t.get_rect(center=(bp_x + bp_w // 2, bp_y + 62)))
        ml = self.f_tiny.render("SCORE MULTIPLIER", True, C_DARK_GOLD)
        surf.blit(ml, ml.get_rect(center=(bp_x + bp_w // 2, bp_y + 86)))
        # Risk bar
        risk_frac = min(self.drunk_level / max_drunk, 1.0)
        rw = bp_w - 30
        rx, ry = bp_x + 15, bp_y + 108
        pygame.draw.rect(surf, (30, 15, 0), (rx, ry, rw, 10))
        rc = C_GREEN if risk_frac < 0.4 else (C_GOLD if risk_frac < 0.7 else C_RED)
        pygame.draw.rect(surf, rc, (rx, ry, int(rw * risk_frac), 10))
        pygame.draw.rect(surf, C_DARK_GOLD, (rx, ry, rw, 10), 1)
        risk_label = "LOW" if risk_frac < 0.33 else ("MEDIUM" if risk_frac < 0.66 else ("HIGH" if risk_frac < 0.9 else "EXTREME"))
        rl = self.f_tiny.render(f"RISK: {risk_label}", True, rc)
        surf.blit(rl, rl.get_rect(center=(bp_x + bp_w // 2, bp_y + 126)))

        # Drink history list
        for j, dh in enumerate(self.drink_history):
            dht = self.f_tiny.render(f"+ {dh['name']}", True, dh["color"])
            surf.blit(dht, dht.get_rect(center=(bp_x + bp_w // 2, bp_y + 148 + j * 13)))

        # ── Bottom bar ────────────────────────────────────────────────────────
        pygame.draw.rect(surf, C_WOOD, (0, H - 60, W, 60))
        pygame.draw.line(surf, C_DARK_GOLD, (0, H - 60), (W, H - 60), 2)
        controls = [
            "← → : SELECT DRINK",
            "ENTER/SPACE : ADD",
            "BACKSPACE : REMOVE LAST",
            "R : START RACE",
        ]
        for j, c in enumerate(controls):
            ct = self.f_tiny.render(c, True, C_DARK_GOLD)
            surf.blit(ct, (20 + j * 210, H - 38))

        # Start button
        btn_col = C_DARK_GOLD if self.drink_history else (60, 40, 0)
        draw_round_rect(surf, btn_col, (W - 175, H - 50, 160, 38), 6)
        bt = self.f_med.render("START RACE  R", True, C_DARK if self.drink_history else (80, 60, 20))
        surf.blit(bt, bt.get_rect(center=(W - 95, H - 31)))

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

        # Spawn
        self.spawn_timer += 1
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            otype = random.choice(OBS_TYPES)
            lane  = random.randint(0, 2)
            self.obstacles.append(Obstacle(lane, otype))
            if random.random() < 0.22:
                self.guards.append(Guard(random.randint(0, 2)))

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
        all_objs = [(obs.depth, obs) for obs in self.obstacles] + \
                   [(g.depth,   g)   for g   in self.guards]
        all_objs.sort(key=lambda x: -x[0])
        for _, obj in all_objs:
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
        # ── 1. SKY — smooth gradient ──────────────────────────────────────────
        for i in range(HORIZON_Y):
            t   = i / HORIZON_Y
            col = tuple(int(C_SKY_TOP[c] + (C_SKY_BOT[c] - C_SKY_TOP[c]) * t) for c in range(3))
            pygame.draw.line(surf, col, (0, i), (W, i))

        # ── 2. CLOUDS (slow scroll) ───────────────────────────────────────────
        cloud_positions = [
            (120, 40, 110, 28),
            (380, 25, 140, 32),
            (650, 55, 95,  22),
            (820, 35, 120, 26),
        ]
        cloud_surf = pygame.Surface((W + 300, HORIZON_Y), pygame.SRCALPHA)
        for (bx, by, cw, ch) in cloud_positions:
            cx_off = int((self.bg_offset * 0.18) % (W + 300))
            for puff in [(0, ch//3, cw, ch), (cw//5, 0, int(cw*0.6), int(ch*1.2)),
                         (int(cw*0.55), ch//5, int(cw*0.55), int(ch*0.9))]:
                pygame.draw.ellipse(cloud_surf, (255, 255, 255, 38),
                                    (bx - cx_off + puff[0], by + puff[1], puff[2], puff[3]))
        surf.blit(cloud_surf, (0, 0))

        # ── 3. SUN glow at horizon ────────────────────────────────────────────
        glow = pygame.Surface((W, 80), pygame.SRCALPHA)
        for r in range(220, 0, -12):
            a = max(0, 28 - r // 9)
            pygame.draw.ellipse(glow, (255, 190, 60, a),
                                (W // 2 - r, 40 - r // 5, r * 2, r // 2))
        surf.blit(glow, (0, HORIZON_Y - 40))

        # ── 4. GRANDSTANDS ────────────────────────────────────────────────────
        # Draw behind the horizon line, scrolling
        stand_h = 70
        for i in range(26):
            sx  = int((i * 64 + self.bg_offset * 0.35) % (W + 64)) - 32
            sh2 = 30 + (i % 5) * 8
            # Stand body
            col = (12 + (i % 4) * 5, 10 + (i % 3) * 3, 18 + (i % 2) * 6)
            pygame.draw.rect(surf, col, (sx, HORIZON_Y - sh2, 58, sh2))
            # Roof lip
            roof_col = (col[0] + 15, col[1] + 10, col[2] + 20)
            pygame.draw.rect(surf, roof_col, (sx - 2, HORIZON_Y - sh2, 62, 5))
            # Crowd dots
            if sh2 > 20:
                dot_colors = [(220, 60, 60), (60, 180, 60), (60, 60, 220),
                              (220, 200, 60), (200, 200, 200)]
                for di in range(4):
                    for dj in range(2):
                        dc = dot_colors[(i * 3 + di + dj) % len(dot_colors)]
                        pygame.draw.circle(surf, dc,
                                           (sx + 8 + di * 13, HORIZON_Y - sh2 + 8 + dj * 10), 3)

        # ── 5. GRASS (full ground fill first) ────────────────────────────────
        for i in range(HORIZON_Y, H):
            t   = (i - HORIZON_Y) / (H - HORIZON_Y)
            col = tuple(int(C_GRASS[c] + (C_GRASS2[c] - C_GRASS[c]) * t) for c in range(3))
            pygame.draw.line(surf, col, (0, i), (W, i))

        # ── 6. TRACK — perspective trapezoid stripes ──────────────────────────
        # Compute left/right track edges at feet and horizon
        edge_off = 0.55   # fraction of lane-width to extend outside lane 0 / lane 2
        def track_edges(depth):
            lx = lane_to_x(0, depth) - lane_pixel_width(depth) * edge_off
            rx = lane_to_x(2, depth) + lane_pixel_width(depth) * edge_off
            return lx, rx

        # Alternating dirt strips scrolling toward camera
        stripe_count = 20
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
            col = C_TRACK if i % 2 == 0 else C_TRACK2
            pygame.draw.polygon(surf, col, [
                (lx1, y1), (rx1, y1), (rx0, y0), (lx0, y0)
            ])

        # Track edge kerb — red/white alternating
        kerb_count = 14
        for i in range(kerb_count + 2):
            d0 = max(0.0, (i / kerb_count) - (self.bg_offset * 0.022) % (1.0 / kerb_count))
            d1 = max(0.0, ((i + 1) / kerb_count) - (self.bg_offset * 0.022) % (1.0 / kerb_count))
            if d0 >= 1.0:
                continue
            d1 = min(d1, 0.99)
            kerb_col = (210, 30, 30) if i % 2 == 0 else (240, 240, 240)
            lx0, rx0 = track_edges(d0)
            lx1, rx1 = track_edges(d1)
            lkw0 = lane_pixel_width(d0) * 0.18
            lkw1 = lane_pixel_width(d1) * 0.18
            y0, y1 = depth_to_y(d0), depth_to_y(d1)
            # Left kerb
            pygame.draw.polygon(surf, kerb_col, [
                (lx1 - lkw1, y1), (lx1, y1), (lx0, y0), (lx0 - lkw0, y0)
            ])
            # Right kerb
            pygame.draw.polygon(surf, kerb_col, [
                (rx1, y1), (rx1 + lkw1, y1), (rx0 + lkw0, y0), (rx0, y0)
            ])

        # ── 7. LANE DIVIDER LINES ─────────────────────────────────────────────
        # Solid white outer edges
        for side in range(2):
            lane_i = 0 if side == 0 else 2
            off    = -0.5 if side == 0 else 0.5
            near_x = int(lane_to_x(lane_i, 0.0) + lane_pixel_width(0.0) * off)
            far_x  = int(lane_to_x(lane_i, 0.97) + lane_pixel_width(0.97) * off)
            pygame.draw.line(surf, (220, 210, 180), (far_x, HORIZON_Y), (near_x, H), 3)

        # Dashed white centre dividers (scrolling)
        dash_d_span = 0.065
        gap_frac    = 0.45
        for gap_lane in range(2):   # divider between lanes 0-1 and 1-2
            d_off = (self.bg_offset * 0.022) % dash_d_span
            for step in range(18):
                d_start = step * dash_d_span - d_off
                d_end   = d_start + dash_d_span * gap_frac
                d_start = max(0.01, d_start)
                d_end   = min(0.98, d_end)
                if d_start >= d_end:
                    continue
                # X midpoint between gap_lane and gap_lane+1
                x0 = int((lane_to_x(gap_lane, d_start) + lane_to_x(gap_lane + 1, d_start)) / 2)
                x1 = int((lane_to_x(gap_lane, d_end)   + lane_to_x(gap_lane + 1, d_end))   / 2)
                y0 = int(depth_to_y(d_start))
                y1 = int(depth_to_y(d_end))
                lw = max(1, int(lane_pixel_width(d_start) * 0.06))
                pygame.draw.line(surf, (230, 220, 180), (x0, y0), (x1, y1), lw)

        # ── 8. HORIZON LINE ───────────────────────────────────────────────────
        pygame.draw.line(surf, (40, 30, 20), (0, HORIZON_Y), (W, HORIZON_Y), 2)

    def _draw_player(self, surf):
        """Draw the player character at the bottom-centre of the current lane."""
        px     = int(lane_to_x(self.player_lane, 0.0) + self.stumble_dx)
        ground = H - 8
        bob    = int(math.sin(self.bg_offset * 0.38) * (0 if self.is_ducking else 4))
        jy     = int(self.player_y)   # negative when in air

        if self.is_ducking:
            # ── Crouched ──────────────────────────────────────────────────────
            bw, bh = 58, 30
            by = ground - bh + bob

            # Ground shadow
            sh = pygame.Surface((bw + 20, 14), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 80), (0, 0, bw + 20, 14))
            surf.blit(sh, (px - bw // 2 - 10, ground - 4))

            # Legs splayed out
            pygame.draw.ellipse(surf, (44, 62, 80), (px - bw // 2 - 8, by + bh // 2, bw + 16, bh // 2 + 4))
            # Torso
            pygame.draw.rect(surf, (44, 62, 80), (px - bw // 2, by, bw, bh), border_radius=8)
            # Jockey shirt stripe
            pygame.draw.rect(surf, (220, 50, 50),  (px - bw // 2 + 3, by + 4,  bw - 6, 9), border_radius=4)
            pygame.draw.rect(surf, (240, 240, 60),  (px - bw // 2 + 3, by + 14, bw - 6, 6), border_radius=3)
            # Head tucked forward
            head_r = 15
            pygame.draw.circle(surf, (210, 165, 120), (px + bw // 4, by - head_r + 4), head_r)
            # Helmet
            pygame.draw.ellipse(surf, (180, 40, 40), (px + bw // 4 - head_r, by - head_r * 2 + 2, head_r * 2, head_r + 4))
            pygame.draw.rect(surf, (160, 30, 30),   (px + bw // 4 - head_r - 2, by - head_r + 2, head_r * 2 + 4, 5), border_radius=2)

        else:
            # ── Standing / running ────────────────────────────────────────────
            bw, bh = 40, 62
            by = ground - bh + bob + jy

            # Ground shadow (shrinks when jumping)
            shadow_scale = max(0.3, 1.0 - abs(jy) / 120)
            sw = int((bw + 24) * shadow_scale)
            sh_surf = pygame.Surface((sw + 4, 14), pygame.SRCALPHA)
            pygame.draw.ellipse(sh_surf, (0, 0, 0, int(80 * shadow_scale)), (0, 0, sw + 4, 14))
            surf.blit(sh_surf, (px - sw // 2, ground - 4))

            # Animated legs
            kick = int(math.sin(self.bg_offset * 0.38) * 14)
            leg_w = 10
            # Left leg
            pygame.draw.polygon(surf, (30, 45, 60), [
                (px - 10, by + bh),
                (px - 10 + leg_w, by + bh),
                (px - 8  + leg_w + kick, ground),
                (px - 8  + kick,         ground),
            ])
            # Right leg
            pygame.draw.polygon(surf, (30, 45, 60), [
                (px + 10 - leg_w, by + bh),
                (px + 10, by + bh),
                (px + 8  - kick,         ground),
                (px + 8  - leg_w - kick, ground),
            ])
            # Boots
            boot_col = (25, 18, 10)
            pygame.draw.ellipse(surf, boot_col, (px - 20 + kick, ground - 5, 18, 10))
            pygame.draw.ellipse(surf, boot_col, (px + 2  - kick, ground - 5, 18, 10))

            # Torso
            pygame.draw.rect(surf, (44, 62, 80), (px - bw // 2, by, bw, bh), border_radius=7)

            # Jockey silks — horizontal stripes
            stripe_colors = [(220, 50, 50), (240, 240, 60), (220, 50, 50)]
            for si, sc in enumerate(stripe_colors):
                sy = by + 6 + si * 10
                pygame.draw.rect(surf, sc, (px - bw // 2 + 3, sy, bw - 6, 8), border_radius=3)

            # Arms (running pump)
            arm_swing = int(math.sin(self.bg_offset * 0.38) * 10)
            arm_col   = (44, 62, 80)
            pygame.draw.line(surf, arm_col,
                             (px - bw // 2 + 4, by + 14),
                             (px - bw // 2 - 14, by + 32 - arm_swing), 7)
            pygame.draw.line(surf, arm_col,
                             (px + bw // 2 - 4, by + 14),
                             (px + bw // 2 + 14, by + 32 + arm_swing), 7)
            # Gloved fists
            pygame.draw.circle(surf, (200, 160, 80), (px - bw // 2 - 14, by + 32 - arm_swing), 5)
            pygame.draw.circle(surf, (200, 160, 80), (px + bw // 2 + 14, by + 32 + arm_swing), 5)

            # Head
            head_r = 16
            pygame.draw.circle(surf, (210, 165, 120), (px, by - head_r + 2), head_r)
            # Helmet
            helmet_col = (180, 40, 40)
            pygame.draw.ellipse(surf, helmet_col, (px - head_r, by - head_r * 2 - 2, head_r * 2, head_r + 6))
            # Helmet brim
            pygame.draw.rect(surf, (150, 28, 28), (px - head_r - 3, by - head_r + 2, head_r * 2 + 6, 5), border_radius=2)
            # Goggles
            pygame.draw.ellipse(surf, (60, 120, 180), (px - 13, by - head_r - 3, 11, 8))
            pygame.draw.ellipse(surf, (60, 120, 180), (px + 2,  by - head_r - 3, 11, 8))
            pygame.draw.line(surf, (120, 80, 40), (px - 2, by - head_r), (px + 2, by - head_r), 2)

        # ── Lane position indicators at bottom ────────────────────────────────
        for i in range(3):
            dot_x = int(lane_to_x(i, 0.0))
            active = (i == self.player_lane)
            pygame.draw.circle(surf, (0, 0, 0),  (dot_x, H - 13), 7)
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
