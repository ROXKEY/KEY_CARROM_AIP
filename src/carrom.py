# ====================================================================
# Name: YOUR NAME HERE              Student ID: YOUR STUDENT ID HERE
# 5FTC2067 AI Principles - Mini Project: Carrom (two players, with chance)
# Modes : 1) Player vs Player  2) Player vs AI (Easy)  3) Player vs AI (Hard)
# Levels: 3 boards, pockets get smaller. First to win 2 levels wins.
# Rules : Player 1 = WHITE (bottom), Player 2 / AI = BLACK (top). Pocket all your
#         coins to win a level. Own coin pocketed = shoot again. Striker = foul (turn lost).
# Chance: random coin layout + small random wobble on every shot.
# AI    : Hard AI simulates many shots (with wobble), scores the consequences
#         and plays the one closest to victory.
# Run   : pip install pygame   then   python carrom.py
# Web   : python -m pygbag carrom   (file must be named main.py)
# ====================================================================
import asyncio
import copy
import math
import random
import sys

import pygame

# ---------------------------- constants -----------------------------
WIDTH, HEIGHT, FPS = 900, 680, 60
BX0, BY0, BS = 20, 20, 640                  # board top-left corner and size
BX1, BY1 = BX0 + BS, BY0 + BS
CX, CY = BX0 + BS // 2, BY0 + BS // 2       # board centre
COIN_R, STRIKER_R = 14, 18
COIN_M, STRIKER_M = 1.0, 2.0
FRICTION, STOP_SPEED2 = 0.98, 0.02          # slow-down per step, speed^2 to stop
WALL_E, COIN_E = 0.8, 0.9                   # bounciness
VMAX = 17.0                                 # max striker speed (px per step)
WOBBLE = math.radians(1.5)                  # random aim error = chance element
BASE_OFFSET = 95                            # baseline distance from board edge
XMIN, XMAX = BX0 + 110, BX1 - 110           # striker slides between these x values
MAX_STEPS, STEPS_PER_FRAME = 900, 2
POCKET_R = {1: 40, 2: 34, 3: 28}            # smaller pockets = harder level
BOARD_COLOR = {1: (232, 200, 150), 2: (212, 170, 115), 3: (60, 80, 115)}
LINE_COLOR = {1: (120, 70, 40), 2: (100, 56, 28), 3: (214, 178, 92)}
POCKETS = [(BX0, BY0), (BX1, BY0), (BX0, BY1), (BX1, BY1)]
MODE_NAMES = ["Player vs Player", "Player vs AI (Easy)", "Player vs AI (Hard)"]
GOLD, WHITE_COIN, BLACK_COIN = (255, 214, 102), (245, 242, 231), (40, 40, 50)
AI_XS, AI_ANGLES, AI_POWERS, AI_TRIALS = 5, 13, (0.55, 1.0), 2   # AI search size


# ============================= PHYSICS ===============================
# A round piece on the board (coin or striker).
class Disc:
    # x, y : position   r : radius   m : mass   kind : "white", "black" or "striker"
    def __init__(self, x, y, r, m, kind):
        self.x, self.y, self.vx, self.vy = x, y, 0.0, 0.0
        self.r, self.m, self.kind, self.alive = r, m, kind, True


# Creates the 10 starting coins in a ring; colours are shuffled (chance).
def make_coins():
    kinds = ["white"] * 5 + ["black"] * 5
    random.shuffle(kinds)
    return [Disc(CX + 48 * math.cos(2 * math.pi * i / 10), CY + 48 * math.sin(2 * math.pi * i / 10),
                 COIN_R, COIN_M, k) for i, k in enumerate(kinds)]


# Y position of a player's baseline (player 0 = bottom, player 1 = top).
#   player : 0 or 1
def baseline_y(player):
    return BY1 - BASE_OFFSET if player == 0 else BY0 + BASE_OFFSET


# True if any disc is still moving.
#   discs : list of Disc
def is_moving(discs):
    return any(d.alive and (d.vx != 0.0 or d.vy != 0.0) for d in discs)


# True if a striker at (x, y) would overlap a coin.
#   coins : list of Disc    x, y : striker position
def striker_blocked(coins, x, y):
    return any(c.alive and (c.x - x) ** 2 + (c.y - y) ** 2 < (STRIKER_R + COIN_R) ** 2 for c in coins)


# Moves every disc one step: friction, wall bounces, pockets, collisions.
# Returns the discs pocketed during this step.
#   discs : list of Disc in play      pocket_r : pocket radius of this level
def step(discs, pocket_r):
    pocketed = []
    for d in discs:
        if not d.alive:
            continue
        if d.vx or d.vy:
            d.x, d.y = d.x + d.vx, d.y + d.vy
            d.vx, d.vy = d.vx * FRICTION, d.vy * FRICTION
            if d.vx * d.vx + d.vy * d.vy < STOP_SPEED2:
                d.vx = d.vy = 0.0
        if d.x < BX0 + d.r:                                  # wall bounces
            d.x, d.vx = BX0 + d.r, abs(d.vx) * WALL_E
        elif d.x > BX1 - d.r:
            d.x, d.vx = BX1 - d.r, -abs(d.vx) * WALL_E
        if d.y < BY0 + d.r:
            d.y, d.vy = BY0 + d.r, abs(d.vy) * WALL_E
        elif d.y > BY1 - d.r:
            d.y, d.vy = BY1 - d.r, -abs(d.vy) * WALL_E
        for px, py in POCKETS:                               # fell into a pocket?
            if (d.x - px) ** 2 + (d.y - py) ** 2 < pocket_r ** 2:
                d.alive, d.vx, d.vy = False, 0.0, 0.0
                pocketed.append(d)
                break
    for i, a in enumerate(discs):                            # disc-to-disc collisions
        if not a.alive:
            continue
        for b in discs[i + 1:]:
            dx, dy = b.x - a.x, b.y - a.y
            rr = a.r + b.r
            dist2 = dx * dx + dy * dy
            if not b.alive or dist2 >= rr * rr or dist2 == 0:
                continue
            dist = math.sqrt(dist2)
            nx, ny = dx / dist, dy / dist
            inv_a, inv_b = 1.0 / a.m, 1.0 / b.m
            total = inv_a + inv_b
            push = (rr - dist) / total                       # separate overlapping discs
            a.x, a.y, b.x, b.y = a.x - nx * push * inv_a, a.y - ny * push * inv_a, \
                b.x + nx * push * inv_b, b.y + ny * push * inv_b
            closing = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny
            if closing > 0:                                  # bounce (impulse)
                j = (1 + COIN_E) * closing / total
                a.vx, a.vy = a.vx - j * inv_a * nx, a.vy - j * inv_a * ny
                b.vx, b.vy = b.vx + j * inv_b * nx, b.vy + j * inv_b * ny
    return pocketed


# Runs a whole shot until everything stops. Returns every disc pocketed.
#   discs : list of Disc (modified in place)      pocket_r : pocket radius
def simulate(discs, pocket_r):
    pocketed = []
    for _ in range(MAX_STEPS):
        pocketed += step(discs, pocket_r)
        if not is_moving(discs):
            break
    return pocketed


# ============================== AI ===================================
# Scores one possible shot by simulating it. Higher = closer to victory.
#   coins : all coins     x, y : striker start     angle : direction (radians)
#   power : 0..1 of VMAX  player : who shoots (0 white, 1 black)     pocket_r : pocket radius
def evaluate_shot(coins, x, y, angle, power, player, pocket_r):
    discs = [copy.copy(c) for c in coins if c.alive]
    striker = Disc(x, y, STRIKER_R, STRIKER_M, "striker")
    striker.vx, striker.vy = math.cos(angle) * VMAX * power, math.sin(angle) * VMAX * power
    discs.append(striker)
    pocketed = simulate(discs, pocket_r)
    own = "white" if player == 0 else "black"
    score = 0.0
    for d in pocketed:
        score += -15 if d.kind == "striker" else (10 if d.kind == own else -8)
    if not any(d.alive and d.kind == own for d in discs):
        score += 100                                         # I win
    if not any(d.alive and d.kind not in (own, "striker") for d in discs):
        score -= 100                                         # the opponent wins
    for d in discs:                                          # my coins near pockets = good
        if d.alive and d.kind != "striker":
            near = min(math.hypot(d.x - px, d.y - py) for px, py in POCKETS)
            score += -0.004 * near if d.kind == own else 0.004 * near
    return score


# Hard AI: tries many shots, simulates each a few times with random wobble and
# returns the (x, angle, power) with the best average score.
#   coins : all coins     player : the AI's player index     pocket_r : pocket radius
def hard_ai_shot(coins, player, pocket_r):
    y, sy = baseline_y(player), (-1 if player == 0 else 1)
    xs = [XMIN + i * (XMAX - XMIN) / (AI_XS - 1) for i in range(AI_XS)]
    xs = [x for x in xs if not striker_blocked(coins, x, y)] or [CX]
    best, best_score = None, -1e9
    for x in xs:
        for k in range(AI_ANGLES):
            deg = math.radians(25 + k * 130 / (AI_ANGLES - 1))
            angle = math.atan2(sy * math.sin(deg), math.cos(deg))
            for power in AI_POWERS:
                total = sum(evaluate_shot(coins, x, y, angle + random.gauss(0, WOBBLE), power,
                                          player, pocket_r) for _ in range(AI_TRIALS))
                score = total / AI_TRIALS + random.random() * 0.01      # random tie-break
                if score > best_score:
                    best, best_score = (x, angle, power), score
    return best


# Easy AI: aims roughly at one of its own coins with a big aiming error.
#   coins : all coins     player : the AI's player index
def easy_ai_shot(coins, player):
    y = baseline_y(player)
    own = "white" if player == 0 else "black"
    xs = [x for x in range(XMIN, XMAX + 1, 40) if not striker_blocked(coins, x, y)]
    x = random.choice(xs or [CX])
    target = random.choice([c for c in coins if c.alive and c.kind == own])
    angle = math.atan2(target.y - y, target.x - x) + random.gauss(0, math.radians(6))
    return x, angle, random.uniform(0.5, 0.9)


# ============================ GAME CLASS =============================
class Game:
    # Sets up fonts and shows the menu.
    #   screen : the pygame display surface
    def __init__(self, screen):
        self.screen = screen
        self.small = pygame.font.SysFont("segoeui,arial", 16)
        self.font = pygame.font.SysFont("segoeui,arial", 21, bold=True)
        self.big = pygame.font.SysFont("segoeui,arial", 44, bold=True)
        self.state = "menu"                  # menu / play / level_end / game_over
        self.mode, self.level, self.wins = 0, 1, [0, 0]
        self.message, self.drag = [], False
        self.coins, self.striker, self.striker_x, self.winner = make_coins(), None, CX, None

    # Starts a new match in the chosen mode.
    #   mode : 0 = PvP, 1 = AI easy, 2 = AI hard
    def start_match(self, mode):
        self.mode, self.level, self.wins = mode, 1, [0, 0]
        self.start_level()

    # Sets up the board for the current level.
    def start_level(self):
        self.coins = make_coins()
        self.turn = (self.level - 1) % 2     # starting player alternates
        self.message = ["Level %d" % self.level, "Smaller pockets", "each level"]
        self.state = "play"
        self.start_turn()

    # Prepares the next shot for the player whose turn it is.
    def start_turn(self):
        self.phase = "ai_think" if self.is_ai(self.turn) else "aim"
        self.ai_timer, self.drag, self.striker, self.striker_x = 0.0, False, None, CX
        self.discs, self.shot_pocketed = [], []

    # True if the given player is the computer.
    #   player : 0 or 1
    def is_ai(self, player):
        return player == 1 and self.mode in (1, 2)

    # Display name of a player.
    #   player : 0 or 1
    def name(self, player):
        return "Player 1" if player == 0 else ["Player 2", "AI (Easy)", "AI (Hard)"][self.mode]

    # Fires the striker.
    #   x : start x     angle : direction in radians     power : 0..1 of VMAX
    def fire(self, x, angle, power):
        angle += random.gauss(0, WOBBLE)     # chance: nobody aims perfectly
        s = Disc(x, baseline_y(self.turn), STRIKER_R, STRIKER_M, "striker")
        s.vx, s.vy = math.cos(angle) * VMAX * power, math.sin(angle) * VMAX * power
        self.striker = s
        self.discs = [c for c in self.coins if c.alive] + [s]
        self.shot_pocketed, self.phase, self.message = [], "moving", []

    # Called when everything has stopped: scores the shot and picks who goes next.
    def end_shot(self):
        p = self.turn
        own = "white" if p == 0 else "black"
        foul = any(d.kind == "striker" for d in self.shot_pocketed)
        own_cnt = sum(1 for d in self.shot_pocketed if d.kind == own)
        opp_cnt = sum(1 for d in self.shot_pocketed if d.kind not in (own, "striker"))
        notes = []
        if foul:
            notes += ["FOUL! Striker in", "pocket - turn lost"]
        if own_cnt:
            notes.append("+%d own coin(s)" % own_cnt)
        if opp_cnt:
            notes.append("%d coin(s) to rival" % opp_cnt)
        left = [sum(1 for c in self.coins if c.alive and c.kind == k) for k in ("white", "black")]
        if left[0] == 0 or left[1] == 0:                     # someone pocketed all their coins
            self.winner = p if left[0] == left[1] else (0 if left[0] == 0 else 1)
            self.wins[self.winner] += 1
            done = self.wins[self.winner] == 2 or self.level == 3
            self.state = "game_over" if done else "level_end"
            return
        if own_cnt and not foul:
            notes.append("Shoot again!")
        else:
            self.turn = 1 - p
        self.message = notes or ["No coin pocketed"]
        self.start_turn()

    # Advances physics and lets the AI move (called every frame).
    def update(self):
        if self.state != "play":
            return
        if self.phase == "aim" and not self.drag:            # striker follows the mouse
            self.striker_x = max(XMIN, min(XMAX, pygame.mouse.get_pos()[0]))
        elif self.phase == "moving":
            for _ in range(STEPS_PER_FRAME):
                self.shot_pocketed += step(self.discs, POCKET_R[self.level])
                if not is_moving(self.discs):
                    self.end_shot()
                    break
        elif self.phase == "ai_think":
            self.ai_timer += 1.0 / FPS
            if self.ai_timer > 0.8:                          # let "thinking..." show first
                if self.mode == 2:
                    self.fire(*hard_ai_shot(self.coins, self.turn, POCKET_R[self.level]))
                else:
                    self.fire(*easy_ai_shot(self.coins, self.turn))

    # Returns (pull_x, pull_y, power) of the current mouse drag (slingshot style).
    def drag_vector(self):
        mx, my = pygame.mouse.get_pos()
        sx, sy = self.striker_x, baseline_y(self.turn)
        return sx - mx, sy - my, min(math.hypot(sx - mx, sy - my), 160) / 160.0

    # Rectangles of the three menu buttons.
    def menu_buttons(self):
        return [pygame.Rect(WIDTH // 2 - 250, 200 + i * 85, 500, 68) for i in range(3)]

    # Handles keyboard and mouse events.
    #   event : a pygame event
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.state = "menu"
            elif self.state == "menu" and event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.start_match(event.key - pygame.K_1)
            elif self.state == "level_end" and event.key == pygame.K_SPACE:
                self.level += 1
                self.start_level()
            elif self.state == "game_over" and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self.state = "menu"
        elif self.state == "menu" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self.menu_buttons()):
                if rect.collidepoint(event.pos):
                    self.start_match(i)
        elif self.state == "play" and self.phase == "aim":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.drag = not striker_blocked(self.coins, self.striker_x, baseline_y(self.turn))
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag:
                self.drag = False
                dx, dy, power = self.drag_vector()
                if power > 0.06:                             # tiny pulls are cancelled
                    self.fire(self.striker_x, math.atan2(dy, dx), power)

    # ---------------------------- drawing ---------------------------
    # Draws text.
    #   msg : text   font : pygame font   color : colour   pos : position   anchor : which point pos refers to
    def text(self, msg, font, color, pos, anchor="center"):
        img = font.render(msg, True, color)
        self.screen.blit(img, img.get_rect(**{anchor: pos}))

    # Draws one coin or striker with shading.
    #   x, y : centre     kind : "white", "black" or "striker"     bad : striker in a blocked spot
    def draw_disc(self, x, y, kind, bad=False):
        scr, x, y = self.screen, int(x), int(y)
        r = STRIKER_R if kind == "striker" else COIN_R
        pygame.draw.circle(scr, tuple(int(v * 0.65) for v in BOARD_COLOR[self.level]), (x + 3, y + 4), r)  # shadow
        face = {"white": WHITE_COIN, "black": BLACK_COIN, "striker": (235, 90, 90) if bad else GOLD}[kind]
        rim = {"white": (150, 140, 120), "black": (0, 0, 0), "striker": (150, 100, 10)}[kind]
        pygame.draw.circle(scr, rim, (x, y), r)
        pygame.draw.circle(scr, face, (x, y), r - 3)
        pygame.draw.circle(scr, rim, (x, y), int(r * 0.55), 1)
        pygame.draw.circle(scr, (255, 255, 255), (x - r // 3, y - r // 3), max(2, r // 6))  # gloss

    # Draws the menu screen.
    def draw_menu(self):
        self.screen.fill((30, 34, 52))
        self.text("CARROM  -  win 2 of 3 levels", self.big, GOLD, (WIDTH // 2, 110))
        for i, rect in enumerate(self.menu_buttons()):
            hover = rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(self.screen, (66, 78, 114) if hover else (40, 48, 74), rect, border_radius=14)
            pygame.draw.rect(self.screen, GOLD if hover else (90, 100, 135), rect, 2, border_radius=14)
            self.text("%d   %s" % (i + 1, MODE_NAMES[i]), self.font, (255, 255, 255), rect.center)
        for i, line in enumerate(["Slide the striker with the mouse, click and drag BACK, release to shoot",
                                  "Own coin pocketed = shoot again.  Striker pocketed = foul.  P1 = white, P2 = black"]):
            self.text(line, self.small, (200, 205, 225), (WIDTH // 2, 500 + i * 28))

    # Draws the board, coins, striker and aiming guide.
    def draw_board(self):
        scr, lv = self.screen, self.level
        scr.fill((26, 30, 44))
        board = pygame.Rect(BX0, BY0, BS, BS)
        pygame.draw.rect(scr, (110, 68, 36), pygame.Rect(BX0 - 14, BY0 - 14, BS + 28, BS + 28), border_radius=14)
        pygame.draw.rect(scr, BOARD_COLOR[lv], board)
        line = LINE_COLOR[lv]
        for p in (0, 1):                                     # baselines with end circles
            y = baseline_y(p)
            for dy in (-STRIKER_R - 4, STRIKER_R + 4):
                pygame.draw.line(scr, line, (XMIN, y + dy), (XMAX, y + dy), 2)
            for x in (XMIN, XMAX):
                pygame.draw.circle(scr, line, (x, y), STRIKER_R + 4, 2)
        pygame.draw.circle(scr, line, (CX, CY), 78, 2)
        pygame.draw.circle(scr, (180, 50, 50), (CX, CY), 9)
        scr.set_clip(board)                                  # pockets (quarter circles)
        for px, py in POCKETS:
            pygame.draw.circle(scr, (110, 68, 36), (px, py), POCKET_R[lv] + 5)
            pygame.draw.circle(scr, (12, 12, 16), (px, py), POCKET_R[lv])
        scr.set_clip(None)

        sy = baseline_y(self.turn)
        for c in self.coins:
            if c.alive:
                self.draw_disc(c.x, c.y, c.kind)
        if self.state == "play" and self.phase == "aim":
            bad = striker_blocked(self.coins, self.striker_x, sy)
            self.draw_disc(self.striker_x, sy, "striker", bad)
            if self.drag:
                self.draw_aim_guide()
        elif self.state == "play" and self.phase == "ai_think":
            self.draw_disc(CX, sy, "striker")
        elif self.striker is not None and self.striker.alive:
            self.draw_disc(self.striker.x, self.striker.y, "striker")

    # Draws the dotted aiming line and the slingshot band while dragging.
    def draw_aim_guide(self):
        dx, dy, power = self.drag_vector()
        length = math.hypot(dx, dy) or 1.0
        sx, sy = self.striker_x, baseline_y(self.turn)
        color = (int(70 + 175 * power), int(225 - 145 * power), 90)   # green -> red
        for i in range(1, int((70 + power * 260) // 16) + 1):
            pygame.draw.circle(self.screen, color, (sx + dx / length * i * 16, sy + dy / length * i * 16), 4)
        pygame.draw.line(self.screen, (255, 255, 255), (sx, sy), pygame.mouse.get_pos(), 2)

    # Draws one player's card in the side panel (coin tray + levels won).
    #   p : 0 or 1     rect : where to draw the card
    def draw_player_card(self, p, rect):
        active = self.state == "play" and self.turn == p
        pygame.draw.rect(self.screen, (46, 56, 86) if active else (28, 33, 50), rect, border_radius=12)
        pygame.draw.rect(self.screen, GOLD if active else (70, 80, 110), rect, 3 if active else 2, border_radius=12)
        kind = "white" if p == 0 else "black"
        self.text(self.name(p), self.font, (255, 255, 255), (rect.x + 14, rect.y + 22), "midleft")
        self.text(kind.upper() + " coins", self.small, (170, 182, 210), (rect.x + 14, rect.y + 44), "midleft")
        left = sum(1 for c in self.coins if c.alive and c.kind == kind)
        for k in range(5):                                   # coin tray
            pos = (rect.x + 24 + k * 34, rect.y + 76)
            if k < left:
                pygame.draw.circle(self.screen, WHITE_COIN if p == 0 else BLACK_COIN, pos, 12)
                pygame.draw.circle(self.screen, (150, 150, 150), pos, 12, 2)
            else:
                pygame.draw.circle(self.screen, (84, 94, 118), pos, 12, 2)
        self.text("Levels won: %d" % self.wins[p], self.small, GOLD, (rect.x + 14, rect.y + 106), "midleft")

    # Draws the side panel: level, players, turn, power bar and message.
    def draw_panel(self):
        scr, cx = self.screen, 782
        pygame.draw.rect(scr, (16, 20, 32), pygame.Rect(676, 20, 212, 640), border_radius=16)
        self.text("LEVEL %d / 3" % self.level, self.font, GOLD, (cx, 50))
        self.draw_player_card(0, pygame.Rect(688, 90, 188, 126))
        self.draw_player_card(1, pygame.Rect(688, 230, 188, 126))
        if self.state == "play":
            self.text("%s's turn" % self.name(self.turn), self.font, GOLD, (cx, 390))
            hint = {"aim": "Drag back, release", "ai_think": "Thinking...", "moving": "Shot in play..."}[self.phase]
            self.text(hint, self.small, (200, 210, 235), (cx, 414))
        power = self.drag_vector()[2] if self.drag else 0.0
        self.text("Power: %d%%" % round(power * 100), self.font, (255, 255, 255), (cx, 460))
        for i, line in enumerate(self.message):              # status message
            self.text(line, self.small, (206, 224, 255), (696, 510 + i * 22), "midleft")

    # Draws the card shown between levels and at the end of the match.
    def draw_overlay(self):
        dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        self.screen.blit(dim, (0, 0))
        box = pygame.Rect(0, 0, 560, 240)
        box.center = (CX, HEIGHT // 2)
        pygame.draw.rect(self.screen, (16, 20, 32), box, border_radius=22)
        pygame.draw.rect(self.screen, GOLD, box, 3, border_radius=22)
        if self.state == "level_end":
            self.text("%s wins Level %d!" % (self.name(self.winner), self.level), self.big, (255, 255, 255), (CX, box.y + 80))
            self.text("Press SPACE for Level %d (smaller pockets)" % (self.level + 1), self.font, GOLD, (CX, box.y + 160))
        else:
            champ = 0 if self.wins[0] > self.wins[1] else 1
            self.text("%s WINS!" % self.name(champ).upper(), self.big, GOLD, (CX, box.y + 80))
            self.text("Final score  %d - %d    (SPACE = menu)" % tuple(self.wins), self.font, (255, 255, 255), (CX, box.y + 160))

    # Draws whichever screen is active.
    def draw(self):
        if self.state == "menu":
            self.draw_menu()
            return
        self.draw_board()
        self.draw_panel()
        if self.state in ("level_end", "game_over"):
            self.draw_overlay()


# =============================== MAIN ================================
# Creates the window and runs the game loop (async so it can run in a browser).
async def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Carrom")
    clock = pygame.time.Clock()
    game = Game(screen)
    while True:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            game.handle_event(event)
        game.update()
        game.draw()
        pygame.display.flip()
        await asyncio.sleep(0)                               # lets the browser breathe


asyncio.run(main())