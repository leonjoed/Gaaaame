# Mechanik-Prototyp - Strichmaennchen-Roguevania-Testbett (Python + pygame, keine Assets)
import os, sys, math, random, traceback
import pygame, asyncio, time

# ===================== TUNING (alles hier anpassen) =====================
SCREEN_W, SCREEN_H, FPS, TILE = 960, 540, 60, 32
MOVE  = dict(max_speed=4.2, accel=0.6, decel=0.5, air_accel=0.42, air_decel=0.22)  # ~0,12 s bis Vollspeed
JUMP  = dict(velocity=-8.6, gravity=0.32, fall_gravity=0.36, max_fall=7.5,
             cut_mult=0.5, coyote=8, buffer=9, double_jump_vel=-7.0, air_jumps=1,
             apex_threshold=1.5, apex_mult=0.5)  # Scheitel: halbe Schwerkraft bei gehaltenem Sprung
WALL  = dict(slide_speed=1.6, jump_vx=4.6, jump_vy=-7.4, lock_frames=10, stick_frames=8)
DASH  = dict(speed=13.0, frames=9, cooldown=40, iframes=10)
DROP  = dict(frames=12)
BLASTER = dict(cooldown=7, speed=11.0, damage=6, knock=2.0, life=60, radius=3)
CHARGED = dict(hold_frames=36, speed=9.2, damage=30, knock=9.0, life=80, radius=8, pierce=True)
MELEE = [dict(damage=12, knock=4.0, active=(4, 9), total=16, lunge=3.0, reach=34, hitstop=4),
         dict(damage=14, knock=5.0, active=(4, 9), total=16, lunge=3.5, reach=36, hitstop=5),
         dict(damage=24, knock=10.0, active=(5, 11), total=24, lunge=5.0, reach=42, hitstop=8)]
MELEE_COMBO_WINDOW = 14
PLAYER = dict(hp=100, w=20, h=44, iframes=60, hurt_knock=6.0, fall_damage=15, spike_damage=20)
WALKER = dict(hp=30, w=26, h=30, speed=1.0, charge_speed=3.3, sight=180, contact=10, weight=1.0)
FLYER  = dict(hp=20, r=13, keep_dist=200, speed=1.7, shoot_cd=110, bullet_speed=2.7, bullet_dmg=10, sight=420, weight=1.4,
              bob=8, rise=32, hover_frames=170, rise_frames=55, descend_frames=45)
BRUTE  = dict(hp=90, w=40, h=56, speed=0.6, sight=200, range=60, windup=50, strike=10, recover=55,
              damage=30, contact=12, weight=0.35)
CAMERA = dict(lerp=0.08, lookahead=130, look_lerp=0.04, vlerp=0.06)
COLORS = dict(bg=(236, 240, 244), tile=(70, 80, 98), oneway=(130, 145, 170), spike=(200, 60, 60),
              player=(25, 25, 30), teal=(0, 190, 180), walker=(220, 120, 40), flyer=(140, 80, 200),
              brute=(90, 110, 70), enemy_shot=(230, 50, 90), flag=(240, 190, 30), text=(30, 30, 40))

LEVEL = [
"...............................................................................................................................#",
"...............................................................................................................................#",
"......................................................#........................................................................#",
"......................................................#...##...................................................................#",
"......................................................#...##...................................................................#",
"......................................................#.--##...................................................................#",
"......................................................#...##...................................................................#",
"........................................f.............#...##...................................................................#",
"......................................................#--.##...................................................................#",
"......................................------..........#...##..................f......................f.........................#",
"......................................................#...##...................................................................#",
"......................................................#.--##...................................................................#",
"..............................------..................#...##..............---------................------......................#",
"......................................................#...##...................................................................#",
"................................###...................#--.##............................#......................................#",
".............................######.......................##............................#..............................###.....#",
".P.............w..........#########............C..........##......w.................b...#.....w.............b.......######..E..#",
"######################..###########....###############################...###########################...#########..##############",
"######################..###########^^^^###############################...###########################^^^#########..##############",
"######################..##############################################...#######################################..##############",
]
SIGNS = [(50, 16, ["Wandsprung: an die Wand springen,", "dann Sprung drücken. Oder: Plattformen", "im Schacht + Doppelsprung"])]
# ========================================================================

BASE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
def clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v
def col(c, a=None):
    c = tuple(int(clamp(x, 0, 255)) for x in c[:3])
    return c if a is None else c + (int(clamp(a, 0, 255)),)
def mix(c1, c2, t):
    t = clamp(t, 0, 1); return col([a + (b - a) * t for a, b in zip(c1, c2)])

class Level:
    def __init__(self):
        self.rows = LEVEL; self.h = len(LEVEL); self.w = max(len(r) for r in LEVEL)
        self.spawns = []; self.checkpoints = []; self.end = None; self.start = (64, 400)
        for y, row in enumerate(self.rows):
            for x, ch in enumerate(row):
                px, py = x * TILE, y * TILE
                if ch == "P": self.start = (px + 16, py + 32)
                elif ch in "wfb": self.spawns.append((ch, px + 16, py + 32))
                elif ch == "C": self.checkpoints.append([px + 16, py + 32, False])
                elif ch == "E": self.end = (px + 16, py + 32)
        self.pw, self.ph = self.w * TILE, self.h * TILE
    def t(self, tx, ty):
        if ty < 0 or tx < 0 or tx >= self.w: return "#"
        if ty >= self.h: return "."
        r = self.rows[ty]; return r[tx] if tx < len(r) else "."
    def solid(self, tx, ty): return self.t(tx, ty) == "#"
    def oneway(self, tx, ty): return self.t(tx, ty) == "-"
    def rect_solid(self, r):
        for ty in range(r.top // TILE, (r.bottom - 1) // TILE + 1):
            for tx in range(r.left // TILE, (r.right - 1) // TILE + 1):
                if self.solid(tx, ty): return True
        return False
    def rect_spike(self, r):
        for ty in range(r.top // TILE, (r.bottom - 1) // TILE + 1):
            for tx in range(r.left // TILE, (r.right - 1) // TILE + 1):
                if self.t(tx, ty) == "^" and r.bottom > ty * TILE + 16: return True
        return False

class Body:
    """Rechteck mit Tile-Kollision (float-Position)."""
    def __init__(self, x, y, w, h): self.x, self.y, self.w, self.h = x - w / 2, y - h, w, h; self.vx = self.vy = 0.0; self.ground = False
    @property
    def rect(self): return pygame.Rect(int(self.x), int(self.y), self.w, self.h)
    @property
    def cx(self): return self.x + self.w / 2
    @property
    def cy(self): return self.y + self.h / 2
    def move(self, lv, drop=False):
        hitx = 0; self.x += self.vx; r = self.rect
        if lv.rect_solid(r):
            if self.vx > 0: self.x = (r.right // TILE) * TILE - self.w; hitx = 1
            elif self.vx < 0: self.x = (r.left // TILE + 1) * TILE; hitx = -1
            self.vx = 0
        oldb = self.y + self.h; self.y += self.vy; r = self.rect; self.ground = False
        if lv.rect_solid(r):
            if self.vy > 0: self.y = (r.bottom // TILE) * TILE - self.h; self.ground = True
            elif self.vy < 0: self.y = (r.top // TILE + 1) * TILE
            self.vy = 0
        elif self.vy >= 0 and not drop:
            ty = (r.bottom - 1) // TILE
            for tx in range(r.left // TILE, (r.right - 1) // TILE + 1):
                if lv.oneway(tx, ty) and oldb <= ty * TILE + 1:
                    self.y = ty * TILE - self.h; self.vy = 0; self.ground = True; break
        if not self.ground and self.vy >= 0:  # Bodenprobe
            p = pygame.Rect(int(self.x), int(self.y + self.h), self.w, 1)
            if lv.rect_solid(p): self.ground = True
        return hitx

class Shot:
    def __init__(s, x, y, vx, vy, dmg, knock, life, r, friendly, pierce=False, charged=False):
        s.x, s.y, s.vx, s.vy, s.dmg, s.knock, s.life, s.r = x, y, vx, vy, dmg, knock, life, r
        s.friendly, s.pierce, s.charged, s.dead, s.hit = friendly, pierce, charged, False, set()

class Player(Body):
    def __init__(s, x, y):
        super().__init__(x, y, PLAYER["w"], PLAYER["h"]); s.hp = PLAYER["hp"]; s.face = 1
        s.coyote = s.buffer = s.dash_t = s.dash_cd = s.inv = s.wall_lock = s.drop_t = 0
        s.air_jumps = JUMP["air_jumps"]; s.wall = 0; s.shot_cd = 0; s.charge = 0
        s.melee_i = -1; s.melee_t = 0; s.combo_t = 0; s.melee_hit = set(); s.anim = 0.0; s.safe = (x, y)
        s.jump_held = False; s.dash_dir = 1
    def update(s, g, inp):
        lv = g.level
        mx = inp.axis(); md = (mx > 0) - (mx < 0)
        for k in ("dash_cd", "inv", "wall_lock", "drop_t", "shot_cd", "combo_t"):
            setattr(s, k, max(0, getattr(s, k) - 1))
        if inp.pressed("jump"): s.buffer = JUMP["buffer"]
        else: s.buffer = max(0, s.buffer - 1)
        # Dash
        if inp.pressed("dash") and s.dash_cd == 0 and s.dash_t == 0:
            s.dash_t = DASH["frames"]; s.dash_cd = DASH["cooldown"]; s.inv = max(s.inv, DASH["iframes"])
            s.dash_dir = md if md else s.face; s.face = s.dash_dir; g.fx_burst(s.cx, s.cy, COLORS["teal"], 6)
        if s.dash_t > 0:
            s.dash_t -= 1; s.vx = DASH["speed"] * s.dash_dir; s.vy = 0
            if g.frame % 2 == 0: g.ghosts.append([s.x, s.y, s.face, 14])
        else:
            if md: s.face = md if s.melee_t == 0 else s.face
            if s.wall_lock == 0:
                tgt = mx * MOVE["max_speed"]
                a = (MOVE["accel"] if mx else MOVE["decel"]) if s.ground else (MOVE["air_accel"] if mx else MOVE["air_decel"])
                s.vx += clamp(tgt - s.vx, -a, a)
            grav = JUMP["gravity"] if s.vy < 0 else JUMP["fall_gravity"]
            if inp.held("jump") and abs(s.vy) < JUMP["apex_threshold"]: grav *= JUMP["apex_mult"]
            s.vy = min(s.vy + grav, JUMP["max_fall"])
            if s.vy < 0 and not inp.held("jump") and s.jump_held: s.vy *= JUMP["cut_mult"]; s.jump_held = False
            # Wandkontakt
            s.wall = 0
            if not s.ground:
                for d in (-1, 1):
                    if lv.rect_solid(s.rect.move(d * 2, 0)):
                        if md == d: s.wall = d; s.wall_stick = WALL["stick_frames"]
                        elif getattr(s, "wall_stick", 0) > 0 and s.vy >= 0:  # weiche Wandhaftung
                            s.wall = d; s.wall_stick -= 1; s.vx = 0
            if s.wall and s.vy > WALL["slide_speed"]: s.vy = WALL["slide_speed"]
            # Springen / Durchfallen
            if s.buffer:
                if inp.held("down") and s.ground and s.on_oneway(lv):
                    s.drop_t = DROP["frames"]; s.buffer = 0; s.y += 2
                elif s.ground or s.coyote:
                    s.vy = JUMP["velocity"]; s.buffer = s.coyote = 0; s.jump_held = True; g.fx_burst(s.cx, s.y + s.h, (150, 150, 150), 4)
                elif s.wall:
                    s.vx = -s.wall * WALL["jump_vx"]; s.vy = WALL["jump_vy"]; s.face = -s.wall
                    s.wall_lock = WALL["lock_frames"]; s.buffer = 0; s.jump_held = True; s.air_jumps = JUMP["air_jumps"]
                elif s.air_jumps > 0:
                    s.air_jumps -= 1; s.vy = JUMP["double_jump_vel"]; s.buffer = 0; s.jump_held = True
                    g.fx_burst(s.cx, s.y + s.h, COLORS["teal"], 5)
        was_ground = s.ground
        s.move(lv, drop=s.drop_t > 0)
        if s.ground: s.coyote = JUMP["coyote"]; s.air_jumps = JUMP["air_jumps"]
        elif was_ground: pass
        else: s.coyote = max(0, s.coyote - 1)
        if s.ground and not lv.rect_solid(s.rect.move(0, 0)):
            # sicherer Punkt: nur auf festem Boden unter beiden Fuessen
            l = lv.solid(int(s.x) // TILE, int(s.y + s.h) // TILE) or lv.oneway(int(s.x) // TILE, int(s.y + s.h) // TILE)
            r = lv.solid(int(s.x + s.w - 1) // TILE, int(s.y + s.h) // TILE) or lv.oneway(int(s.x + s.w - 1) // TILE, int(s.y + s.h) // TILE)
            if l and r and not lv.rect_spike(s.rect.inflate(40, 4)): s.safe = (s.cx, s.y + s.h)
        # Blaster / Ladeschuss
        if inp.held("shoot"):
            s.charge += 1
            if s.shot_cd == 0 and s.charge < 10:
                s.fire(g, False); s.shot_cd = BLASTER["cooldown"]
        else:
            if s.charge >= CHARGED["hold_frames"]: s.fire(g, True)
            s.charge = 0
        # Nahkampf
        if inp.pressed("melee") and (s.melee_t == 0 or s.melee_t < MELEE[s.melee_i]["total"] - MELEE[s.melee_i]["active"][1]):
            s.melee_i = (s.melee_i + 1) % 3 if s.combo_t > 0 or s.melee_t > 0 else 0
            m = MELEE[s.melee_i]; s.melee_t = m["total"]; s.melee_hit = set()
            if s.dash_t == 0: s.vx = s.face * m["lunge"]
        if s.melee_t > 0:
            m = MELEE[s.melee_i]; el = m["total"] - s.melee_t
            if m["active"][0] <= el <= m["active"][1]:
                hb = pygame.Rect(0, 0, m["reach"], 34); hb.midleft = (s.cx, s.cy - 4)
                if s.face < 0: hb.midright = (s.cx, s.cy - 4)
                for e in g.enemies:
                    if e not in s.melee_hit and hb.colliderect(e.rect):
                        s.melee_hit.add(e); e.hurt(g, m["damage"], s.face * m["knock"], melee=True, src_x=s.cx)
                        g.hitstop = max(g.hitstop, m["hitstop"]); g.shake = max(g.shake, 4)
            s.melee_t -= 1
            if s.melee_t == 0: s.combo_t = MELEE_COMBO_WINDOW
        if s.combo_t == 0 and s.melee_t == 0: s.melee_i = -1
        # Gefahren
        if lv.rect_spike(s.rect): g.hurt_player(PLAYER["spike_damage"], -s.face, respawn_safe=True)
        if s.y > lv.ph + 40: g.hurt_player(PLAYER["fall_damage"], 0, respawn_safe=True, force=True)
        s.anim += abs(s.vx) * 0.09 if s.ground else 0.15
    def on_oneway(s, lv):
        ty = int(s.y + s.h) // TILE
        return any(lv.oneway(tx, ty) for tx in range(int(s.x) // TILE, int(s.x + s.w - 1) // TILE + 1))
    def muzzle(s): return (s.cx + s.face * 16, s.y + 17)
    def fire(s, g, charged):
        x, y = s.muzzle()
        if charged:
            c = CHARGED; g.shots.append(Shot(x, y, s.face * c["speed"], 0, c["damage"], c["knock"], c["life"], c["radius"], True, c["pierce"], True))
            g.shake = max(g.shake, 5); g.fx_burst(x, y, COLORS["teal"], 10)
        else:
            b = BLASTER; g.shots.append(Shot(x, y, s.face * b["speed"], random.uniform(-0.3, 0.3), b["damage"], b["knock"], b["life"], b["radius"], True))

class Enemy(Body):
    kind = "?"
    def __init__(s, x, y, w, h, hp):
        super().__init__(x, y, w, h); s.hp = s.maxhp = hp; s.flash = 0; s.face = -1; s.dead = False; s.stun = 0
    def hurt(s, g, dmg, kx, melee=False, src_x=None, shot=None):
        s.hp -= dmg; s.flash = 6; s.stun = 8; s.vx = kx * s.weight; s.vy = -abs(kx) * 0.3 * s.weight
        g.numbers.append([s.cx + random.uniform(-6, 6), s.y - 4, str(int(dmg)), 40, dmg >= 20])
        if s.hp <= 0 and not s.dead: s.dead = True; g.fx_burst(s.cx, s.cy, s.color, 18, big=True); g.shake = max(g.shake, 6)
    def physics(s, g):
        s.vy = min(s.vy + JUMP["fall_gravity"], JUMP["max_fall"]); hx = s.move(g.level)
        if s.y > g.level.ph + 50: s.dead = True
        return hx
    def edge_ahead(s, lv):
        fx = int(s.cx + s.face * (s.w / 2 + 4)) // TILE; fy = int(s.y + s.h + 2) // TILE
        return not (lv.solid(fx, fy) or lv.oneway(fx, fy)) or lv.t(fx, fy) == "^" or lv.solid(fx, int(s.cy) // TILE)

class Walker(Enemy):
    kind = "w"; color = COLORS["walker"]; weight = WALKER["weight"]
    def __init__(s, x, y): super().__init__(x, y, WALKER["w"], WALKER["h"], WALKER["hp"]); s.charging = False
    def update(s, g):
        p = g.player; s.flash = max(0, s.flash - 1)
        if s.stun: s.stun -= 1; s.vx *= 0.85
        else:
            s.charging = abs(p.cx - s.cx) < WALKER["sight"] and abs(p.cy - s.cy) < 50
            if s.charging: s.face = 1 if p.cx > s.cx else -1
            sp = WALKER["charge_speed"] if s.charging else WALKER["speed"]
            if s.ground and s.edge_ahead(g.level): s.face *= -1; sp = 0 if s.charging else sp
            s.vx = s.face * sp
        s.physics(g)
        if s.rect.colliderect(p.rect): g.hurt_player(WALKER["contact"], 1 if p.cx > s.cx else -1)

class Flyer(Enemy):
    kind = "f"; color = COLORS["flyer"]; weight = FLYER["weight"]
    def __init__(s, x, y):
        super().__init__(x, y - 10, FLYER["r"] * 2, FLYER["r"] * 2, FLYER["hp"])
        s.cd = FLYER["shoot_cd"]; s.t = random.random() * 6; s.home = (s.cx, s.cy)
        s.phase, s.phase_t, s.anchor, s.side = "descend", 1, None, -1
    def open_y(s, lv, cy):
        # Blockierte Hoehe nach unten schieben, nicht in eine hoehere Nische ausweichen.
        def blocked(y):
            return lv.rect_solid(pygame.Rect(int(s.cx - s.w / 2), int(y - s.h / 2), s.w, s.h))
        if not blocked(cy): return cy
        for dy in range(4, 180, 4):
            if not blocked(cy + dy): return cy + dy
        return cy
    def update(s, g):
        p = g.player; s.flash = max(0, s.flash - 1); s.t += 0.05
        dx = p.cx - s.cx; d = math.hypot(dx, p.cy - s.cy) or 1
        chest = p.y + 17  # gleiche Hoehe wie Player.muzzle
        if p.ground or s.anchor is None or chest > s.anchor:
            s.anchor = chest  # Sprung nach oben nicht verfolgen
        if s.stun:
            s.stun -= 1; s.vx *= 0.9; s.vy *= 0.9
        elif d < FLYER["sight"]:
            s.face = 1 if dx > 0 else -1
            if abs(dx) > 12: s.side = 1 if s.cx >= p.cx else -1
            goal_x = p.cx + s.side * FLYER["keep_dist"]
            stacked = abs(dx) < (s.w + p.w) / 2 + 14
            if stacked: goal_x = p.cx + s.side * max(FLYER["keep_dist"], 96); s.vx += s.side * 0.35
            s.phase_t -= 1
            if s.phase == "rise":
                target = s.anchor - FLYER["rise"]
                if s.phase_t <= 0: s.phase, s.phase_t = "descend", FLYER["descend_frames"]
            elif s.phase == "descend":
                target = s.anchor
                if abs(s.cy - s.anchor) < 8:  # Uhr erst auf Brusthoehe starten, nicht schon im Anflug
                    s.phase, s.phase_t, s.cd = "hover", FLYER["hover_frames"], FLYER["shoot_cd"]
            else:
                target = s.anchor + math.sin(s.t) * FLYER["bob"]
                if s.phase_t <= 0: s.phase, s.phase_t = "rise", FLYER["rise_frames"]
            if stacked: target = min(target, p.y - s.h / 2 - 6)  # nicht in den Koerper sinken
            target = s.open_y(g.level, target)
            s.vx += clamp((goal_x - s.cx) * 0.02, -0.3, 0.3)
            s.vy += clamp((target - s.cy) * 0.05, -0.3, 0.3)
            aligned = s.phase == "hover" and abs(s.cy - s.anchor) <= FLYER["bob"] + 4 and abs(dx) > 48
            if aligned:
                s.cd -= 1
                if s.cd <= 0:
                    s.cd = FLYER["shoot_cd"]; v = FLYER["bullet_speed"]
                    aim_y = clamp(chest - s.cy, -6, 6); ad = math.hypot(dx, aim_y) or 1
                    g.shots.append(Shot(s.cx, s.cy, dx / ad * v, aim_y / ad * v, FLYER["bullet_dmg"], 4, 200, 6, False))
            else:
                s.cd = max(s.cd, 28)  # Warnring nur auf der Schusslinie
        else:
            s.vx += clamp((s.home[0] - s.cx) * 0.01, -0.1, 0.1)
            s.vy += clamp((s.home[1] - s.cy) * 0.01 + math.sin(s.t) * 0.04, -0.1, 0.1)
        sp = math.hypot(s.vx, s.vy)
        if sp > FLYER["speed"]: s.vx *= FLYER["speed"] / sp; s.vy *= FLYER["speed"] / sp
        s.x += s.vx
        if g.level.rect_solid(s.rect): s.x -= s.vx; s.vx = -s.vx * 0.5
        s.y += s.vy
        if g.level.rect_solid(s.rect): s.y -= s.vy; s.vy = -s.vy * 0.5
        if s.rect.colliderect(p.rect):
            push = (s.w + p.w) / 2 + 6 - abs(s.cx - p.cx)
            if push > 0 and abs(s.cy - p.cy) < (s.h + p.h) / 2:
                s.x += math.copysign(push, s.side or 1)
                if g.level.rect_solid(s.rect): s.x -= math.copysign(push, s.side or 1)
            if s.rect.colliderect(p.rect): g.hurt_player(8, 1 if p.cx > s.cx else -1)

class Brute(Enemy):
    kind = "b"; color = COLORS["brute"]; weight = BRUTE["weight"]
    def __init__(s, x, y): super().__init__(x, y, BRUTE["w"], BRUTE["h"], BRUTE["hp"]); s.state = "walk"; s.st = 0; s.struck = False
    def vulnerable_from(s, src_x, melee):
        if melee or s.state == "recover": return True
        return (src_x - s.cx) * s.face < 0  # von hinten
    def hurt(s, g, dmg, kx, melee=False, src_x=None, shot=None):
        if src_x is not None and not s.vulnerable_from(src_x, melee):
            g.numbers.append([s.cx + s.face * 20, s.y, "Block", 30, False]); g.fx_burst(s.cx + s.face * 22, s.cy, (200, 200, 200), 4)
            if shot: shot.dead = True
            return
        super().hurt(g, dmg, kx, melee, src_x)
        if s.state in ("walk",): s.stun = 4
    def update(s, g):
        p = g.player; s.flash = max(0, s.flash - 1); dx = p.cx - s.cx
        if s.stun: s.stun -= 1; s.vx *= 0.8
        elif s.state == "walk":
            if abs(dx) < BRUTE["sight"] and abs(p.cy - s.cy) < 70: s.face = 1 if dx > 0 else -1
            if abs(dx) < BRUTE["range"] and abs(p.cy - s.cy) < 60: s.state, s.st = "windup", BRUTE["windup"]; s.vx = 0
            else:
                if s.ground and s.edge_ahead(g.level): s.face *= -1
                s.vx = s.face * BRUTE["speed"]
        else:
            s.vx = 0; s.st -= 1
            if s.state == "windup" and s.st <= 0: s.state, s.st, s.struck = "strike", BRUTE["strike"], False; g.shake = max(g.shake, 7)
            elif s.state == "strike":
                hb = pygame.Rect(0, 0, 70, s.h); hb.midleft = (s.cx, s.cy)
                if s.face < 0: hb.midright = (s.cx, s.cy)
                if not s.struck and hb.colliderect(p.rect): s.struck = True; g.hurt_player(BRUTE["damage"], s.face, big=True)
                if s.st <= 0: s.state, s.st = "recover", BRUTE["recover"]
            elif s.state == "recover" and s.st <= 0: s.state = "walk"
        s.physics(g)
        if s.rect.colliderect(p.rect) and s.state != "strike": g.hurt_player(BRUTE["contact"], 1 if dx > 0 else -1)

class Input:
    MAP = {"left": (pygame.K_a, pygame.K_LEFT), "right": (pygame.K_d, pygame.K_RIGHT), "jump": (pygame.K_SPACE, pygame.K_w, pygame.K_UP),
           "down": (pygame.K_s, pygame.K_DOWN), "dash": (pygame.K_LSHIFT, pygame.K_RSHIFT), "shoot": (pygame.K_j,), "melee": (pygame.K_k,),
           "restart": (pygame.K_r,), "help": (pygame.K_h,), "quit": (pygame.K_ESCAPE,)}
    def __init__(s): s.cur = set(); s.prev = set(); s.joy = None
    def held(s, a): return a in s.cur
    def axis(s):
        a = getattr(s, "ax", None)
        if a is not None and abs(a) > 0.01: return clamp(a, -1, 1)
        return (1 if "right" in s.cur else 0) - (1 if "left" in s.cur else 0)
    def pressed(s, a): return a in s.cur and a not in s.prev
    def poll(s):
        s.prev = s.cur; s.cur = set(); s.ax = None; keys = pygame.key.get_pressed(); mb = pygame.mouse.get_pressed()
        for a, ks in s.MAP.items():
            if any(keys[k] for k in ks): s.cur.add(a)
        if mb[0]: s.cur.add("shoot")
        if mb[2]: s.cur.add("melee")
        if s.joy is None and pygame.joystick.get_count(): s.joy = pygame.joystick.Joystick(0)
        if s.joy:
            try:
                ax = s.joy.get_axis(0); s.ax = 0 if abs(ax) < 0.15 else (ax - math.copysign(0.15, ax)) / 0.85; ay = s.joy.get_axis(1); hx, hy = s.joy.get_hat(0) if s.joy.get_numhats() else (0, 0)
                if ax < -0.4 or hx < 0: s.cur.add("left")
                if ax > 0.4 or hx > 0: s.cur.add("right")
                if ay > 0.5 or hy < 0: s.cur.add("down")
                b = lambda i: s.joy.get_numbuttons() > i and s.joy.get_button(i)
                if b(0): s.cur.add("jump")   # A
                if b(1): s.cur.add("dash")   # B
                if b(2): s.cur.add("shoot")  # X
                if b(3): s.cur.add("melee")  # Y
                if b(7): s.cur.add("quit")
            except pygame.error: s.joy = None

class RandomInput(Input):
    def __init__(s, seed=1): super().__init__(); s.rng = random.Random(seed); s.state = set(); s.hold = {}
    def poll(s):
        s.prev = s.cur; r = s.rng
        for a, p in (("right", 0.03), ("left", 0.02), ("jump", 0.06), ("dash", 0.02), ("shoot", 0.03), ("melee", 0.04), ("down", 0.01)):
            if a in s.hold:
                s.hold[a] -= 1
                if s.hold[a] <= 0: del s.hold[a]
            elif r.random() < p: s.hold[a] = r.choice([2, 5, 12, 45, 90]) if a != "shoot" else r.choice([3, 40, 60])
        if "left" in s.hold and "right" in s.hold: del s.hold["left"]
        s.cur = set(s.hold)

class Game:
    def __init__(s, screen, inp):
        s.screen, s.inp = screen, inp; s.level = Level(); s.font = pygame.font.SysFont("arial", 16, bold=True)
        s.big = pygame.font.SysFont("arial", 56, bold=True); s.small = pygame.font.SysFont("arial", 14)
        s.show_help = True; s.frame = 0; s.stats = dict(deaths=0, dashes=0, walljumps=0, charged=0, melee=0, kills=0, falls=0)
        s.checkpoint = s.level.start; s.reset(full=True)
    def reset(s, full=False):
        if full:
            s.checkpoint = s.level.start
            for c in s.level.checkpoints: c[2] = False
        s.player = Player(*s.checkpoint); s.enemies = []
        for k, x, y in s.level.spawns: s.enemies.append({"w": Walker, "f": Flyer, "b": Brute}[k](x, y))
        s.shots = []; s.fx = []; s.numbers = []; s.ghosts = []; s.hitstop = 0; s.shake = 0; s.dead_t = 0; s.won = False
        s.cam = [s.player.cx - SCREEN_W / 2, s.player.cy - SCREEN_H / 2]
    def fx_burst(s, x, y, c, n, big=False):
        for _ in range(n):
            a = random.uniform(0, 6.28); v = random.uniform(1, 6 if big else 3)
            s.fx.append([x, y, math.cos(a) * v, math.sin(a) * v, random.randint(15, 35), c, random.randint(2, 5 if big else 3)])
    def hurt_player(s, dmg, kdir, respawn_safe=False, force=False, big=False):
        p = s.player
        if s.dead_t: return
        if respawn_safe:
            if force: s.stats["falls"] += 1
            p.hp -= dmg; s.numbers.append([p.cx, p.y, str(dmg), 40, True])
            p.x, p.y = p.safe[0] - p.w / 2, p.safe[1] - p.h; p.vx = p.vy = 0; p.inv = PLAYER["iframes"]; p.dash_t = 0
        else:
            if p.inv: return
            p.hp -= dmg; p.inv = PLAYER["iframes"]; p.vx = kdir * PLAYER["hurt_knock"] * (1.6 if big else 1); p.vy = -5; p.dash_t = 0
            s.numbers.append([p.cx, p.y, str(dmg), 40, True]); s.hitstop = max(s.hitstop, 5)
        s.shake = max(s.shake, 8)
        if p.hp <= 0: s.dead_t = 120; s.stats["deaths"] += 1; s.fx_burst(p.cx, p.cy, COLORS["player"], 25, True)
    def update(s):
        s.frame += 1; inp = s.inp
        if inp.pressed("help"): s.show_help = not s.show_help
        if inp.pressed("restart"): s.reset(full=True); return
        if s.dead_t:
            s.dead_t -= 1
            if s.dead_t == 0: s.reset()
            s.update_fx(); return
        if s.won:
            s.update_fx()
            if inp.pressed("jump"): s.reset(full=True)
            return
        if s.hitstop: s.hitstop -= 1; return
        p = s.player
        # Statistik fuer Tests
        if inp.pressed("dash") and p.dash_cd == 0: s.stats["dashes"] += 1
        if inp.pressed("melee"): s.stats["melee"] += 1
        wl = p.wall_lock
        p.update(s, inp)
        if p.wall_lock > wl: s.stats["walljumps"] += 1
        for e in s.enemies: e.update(s)
        for sh in s.shots:
            sh.x += sh.vx; sh.y += sh.vy; sh.life -= 1
            if sh.life <= 0 or s.level.solid(int(sh.x) // TILE, int(sh.y) // TILE): sh.dead = True; s.fx_burst(sh.x, sh.y, (120, 120, 120), 2); continue
            r = pygame.Rect(sh.x - sh.r, sh.y - sh.r, sh.r * 2, sh.r * 2)
            if sh.friendly:
                if sh.charged and sh.life == CHARGED["life"] - 1: s.stats["charged"] += 1
                for e in s.enemies:
                    if e not in sh.hit and not e.dead and r.colliderect(e.rect):
                        sh.hit.add(e); e.hurt(s, sh.dmg, math.copysign(sh.knock, sh.vx), src_x=sh.x - sh.vx * 3, shot=sh)
                        s.hitstop = max(s.hitstop, 2 if not sh.charged else 6)
                        if not sh.pierce: sh.dead = True; break
            elif r.colliderect(p.rect) and not p.inv:
                sh.dead = True; s.hurt_player(sh.dmg, 1 if sh.vx > 0 else -1)
        s.shots = [x for x in s.shots if not x.dead]
        before = len(s.enemies); s.enemies = [e for e in s.enemies if not e.dead]; s.stats["kills"] += before - len(s.enemies)
        for c in s.level.checkpoints:
            if not c[2] and abs(p.cx - c[0]) < 24 and abs(p.y + p.h - c[1]) < 50:
                c[2] = True; s.checkpoint = (c[0], c[1]); s.numbers.append([c[0], c[1] - 70, "Checkpoint!", 70, False]); p.hp = PLAYER["hp"]
        e = s.level.end
        if e and abs(p.cx - e[0]) < 24 and abs(p.y + p.h - e[1]) < 50: s.won = True
        s.update_fx()
        s.look = getattr(s, "look", 0.0); s.look += (p.face * CAMERA["lookahead"] - s.look) * CAMERA["look_lerp"]; look = s.look
        tx = clamp(p.cx + look - SCREEN_W / 2, 0, s.level.pw - SCREEN_W); ty = clamp(p.cy - SCREEN_H * 0.55, 0, s.level.ph - SCREEN_H)
        s.cam[0] += (tx - s.cam[0]) * CAMERA["lerp"]; s.cam[1] += (ty - s.cam[1]) * CAMERA["vlerp"]
    def update_fx(s):
        for f in s.fx: f[0] += f[2]; f[1] += f[3]; f[3] += 0.2; f[4] -= 1
        s.fx = [f for f in s.fx if f[4] > 0]
        for n in s.numbers: n[1] -= 0.7; n[3] -= 1
        s.numbers = [n for n in s.numbers if n[3] > 0]
        for gh in s.ghosts: gh[3] -= 1
        s.ghosts = [g for g in s.ghosts if g[3] > 0]
        s.shake = max(0, s.shake - 1)

    # ---------------- Zeichnen ----------------
    def draw(s):
        sc = s.screen; sc.fill(COLORS["bg"])
        ox = int(s.cam[0] + random.uniform(-s.shake, s.shake) * 0.5); oy = int(s.cam[1] + random.uniform(-s.shake, s.shake) * 0.5)
        lv = s.level
        for i in range(0, lv.pw, 160):  # dezentes Raster als Tiefe
            x = int(i - ox * 0.5) % (SCREEN_W + 160) - 80; pygame.draw.line(sc, (225, 230, 236), (x, 0), (x, SCREEN_H), 2)
        for ty in range(max(0, oy // TILE), min(lv.h, (oy + SCREEN_H) // TILE + 1)):
            for tx in range(max(0, ox // TILE), min(lv.w, (ox + SCREEN_W) // TILE + 2)):
                ch = lv.t(tx, ty); x, y = tx * TILE - ox, ty * TILE - oy
                if ch == "#": pygame.draw.rect(sc, COLORS["tile"], (x, y, TILE, TILE)); pygame.draw.rect(sc, (90, 100, 120), (x, y, TILE, TILE), 1)
                elif ch == "-": pygame.draw.rect(sc, COLORS["oneway"], (x, y, TILE, 7)); pygame.draw.line(sc, (100, 115, 140), (x, y + 7), (x + TILE, y + 7), 1)
                elif ch == "^":
                    for k in range(4): pygame.draw.polygon(sc, COLORS["spike"], [(x + k * 8, y + TILE), (x + k * 8 + 4, y + 14), (x + k * 8 + 8, y + TILE)])
        for c in lv.checkpoints: s.draw_flag(c[0] - ox, c[1] - oy, COLORS["teal"] if c[2] else (160, 160, 160), "C")
        for sx, sy, lines in SIGNS:
            bx = sx * TILE - ox - 40; by = sy * TILE - oy - 150; w = 280
            pygame.draw.line(sc, (120, 100, 60), (bx + 40, by + 60), (bx + 40, sy * TILE - oy + 32), 3)
            pygame.draw.rect(sc, (255, 250, 220), (bx, by, w, 62), border_radius=4); pygame.draw.rect(sc, (120, 100, 60), (bx, by, w, 62), 2, border_radius=4)
            for i, l in enumerate(lines): sc.blit(s.small.render(l, True, COLORS["text"]), (bx + 8, by + 5 + i * 18))
        if lv.end: s.draw_flag(lv.end[0] - ox, lv.end[1] - oy, COLORS["flag"], "Ziel")
        for e in s.enemies: s.draw_enemy(e, ox, oy)
        for gh in s.ghosts: s.draw_stick(gh[0] - ox, gh[1] - oy, gh[2], 0, "dash", alpha=gh[3] * 12, color=COLORS["teal"])
        p = s.player
        if not s.dead_t and not (p.inv and not p.dash_t and s.frame % 6 < 3): s.draw_player(p, ox, oy)
        for sh in s.shots:
            c = COLORS["teal"] if sh.friendly else COLORS["enemy_shot"]
            pygame.draw.circle(sc, c, (int(sh.x - ox), int(sh.y - oy)), sh.r)
            if sh.charged: pygame.draw.circle(sc, (255, 255, 255), (int(sh.x - ox), int(sh.y - oy)), sh.r // 2)
        for f in s.fx: pygame.draw.circle(sc, col(f[5]), (int(f[0] - ox), int(f[1] - oy)), max(1, int(f[6] * f[4] / 35 + 1)))
        for n in s.numbers:
            t = s.font.render(n[2], True, col((220, 40, 40) if n[4] else (40, 40, 40)))
            t.set_alpha(col((0, 0, 0), n[3] * 8)[3]); sc.blit(t, (n[0] - ox - t.get_width() / 2, n[1] - oy))
        s.draw_hud()
    def draw_flag(s, x, y, c, label):
        pygame.draw.line(s.screen, (60, 60, 60), (x, y), (x, y - 64), 3)
        pygame.draw.polygon(s.screen, col(c), [(x, y - 64), (x + 28, y - 56), (x, y - 46)])
        t = s.small.render(label, True, COLORS["text"]); s.screen.blit(t, (x - t.get_width() / 2, y + 2))
    def draw_stick(s, x, y, face, anim, pose, alpha=255, color=None, charge=0, melee=None):
        """x,y = linke obere Ecke des Koerpers (20x44). Prozedurale Gliedmassen per Winkel."""
        c = col(color or COLORS["player"]); surf = pygame.Surface((90, 80), pygame.SRCALPHA); cx, top = 45, 18
        hip = (cx, top + 28); neck = (cx, top + 12); head = (cx, top + 5)
        def limb(o, ang, ln, w=3):
            e = (o[0] + math.sin(ang) * ln * face, o[1] + math.cos(ang) * ln); pygame.draw.line(surf, col(c, alpha), o, e, w); return e
        sw = math.sin(anim)
        if pose == "run": legs = (0.7 * sw, -0.7 * sw); arms = (-0.6 * sw, 0.6 * sw)
        elif pose == "jump": legs = (0.5, -0.3); arms = (2.4, 2.0)
        elif pose == "fall": legs = (0.3, -0.5); arms = (2.6, 2.2)
        elif pose == "dash": legs = (1.0, -0.8); arms = (-1.0, -1.2)
        elif pose == "wall": legs = (0.4, 0.1); arms = (2.8, 2.5)
        else: b = math.sin(anim * 0.5) * 0.05; legs = (0.15, -0.15); arms = (0.25 + b, -0.2 - b)
        shoot_arm = None
        if melee is not None:  # Angriffsbogen
            i, prog = melee[0], melee[1]; base = [(-0.5, 2.4), (2.6, 0.6), (-0.3, 3.0)][i]; shoot_arm = base[0] + (base[1] - base[0]) * clamp(prog, 0, 1)
        elif pose in ("idle", "run", "jump", "fall") and charge >= 0: shoot_arm = None
        pygame.draw.line(surf, col(c, alpha), neck, hip, 3)
        knee_l = limb(hip, legs[0], 10); limb(knee_l, legs[0] - 0.4 if pose != "run" else legs[0] - abs(sw) * 0.8, 10)
        knee_r = limb(hip, legs[1], 10); limb(knee_r, legs[1] - 0.4 if pose != "run" else legs[1] - abs(sw) * 0.8, 10)
        limb(neck, arms[1], 14)
        hand = limb(neck, shoot_arm if shoot_arm is not None else (1.57 if charge > 0 else arms[0]), 15)
        pygame.draw.circle(surf, col(c, alpha), head, 6, 2)
        # Zopf (Pferdeschwanz) nach hinten, schwingt mit
        sway = math.sin(anim * 1.3) * 3 + (6 if pose in ("run", "dash") else 0)
        pygame.draw.lines(surf, col(c, alpha), False, [(head[0] - face * 4, head[1] - 4), (head[0] - face * (10 + sway), head[1] - 2), (head[0] - face * (14 + sway), head[1] + 8)], 3)
        # Handgelenk-Blaster
        pygame.draw.circle(surf, col(COLORS["teal"], alpha), (int(hand[0]), int(hand[1])), 4)
        if charge > 0:
            r = int(3 + 6 * clamp(charge / CHARGED["hold_frames"], 0, 1)); full = charge >= CHARGED["hold_frames"]
            pygame.draw.circle(surf, col((255, 255, 255) if full and (s.frame // 4) % 2 else COLORS["teal"], 150), (int(hand[0]), int(hand[1])), r, 2)
        if melee is not None and melee[2]:
            m = MELEE[melee[0]]; rr = pygame.Rect(0, 0, m["reach"] * 2, 50); rr.center = (cx, top + 18)
            a0, a1 = (-1.2, 1.2) if face > 0 else (math.pi - 1.2, math.pi + 1.2)
            pygame.draw.arc(surf, col(COLORS["teal"], 200), rr, a0, a1, 4)
        s.screen.blit(surf, (int(x + 10 - cx), int(y - top)))
    def draw_player(s, p, ox, oy):
        pose = "dash" if p.dash_t else ("wall" if p.wall and not p.ground else ("jump" if not p.ground and p.vy < 0 else ("fall" if not p.ground else ("run" if abs(p.vx) > 0.6 else "idle"))))
        mel = None
        if p.melee_t > 0:
            m = MELEE[p.melee_i]; el = m["total"] - p.melee_t; mel = (p.melee_i, el / m["active"][1], m["active"][0] <= el <= m["active"][1])
        s.draw_stick(p.x - ox, p.y - oy, p.face if pose != "wall" else -p.wall, p.anim if pose == "run" else s.frame * 0.1, pose, charge=p.charge if p.charge > 10 else 0, melee=mel)
    def draw_enemy(s, e, ox, oy):
        sc = s.screen; r = e.rect.move(-ox, -oy); c = (255, 255, 255) if e.flash else e.color
        if e.kind == "w":
            pygame.draw.rect(sc, col(c), r, border_radius=8)
            ey = r.top + 9; ex = r.centerx + e.face * 6; pygame.draw.circle(sc, (255, 255, 255), (ex, ey), 4); pygame.draw.circle(sc, (0, 0, 0), (ex + e.face, ey), 2)
            if e.charging: pygame.draw.polygon(sc, (0, 0, 0), [(r.centerx - e.face * 4, r.top - 2), (r.centerx + e.face * 8, r.top + 4), (r.centerx - e.face * 4, r.top + 6)])
        elif e.kind == "f":
            pygame.draw.circle(sc, col(c), r.center, e.w // 2)
            wing = math.sin(s.frame * 0.5) * 6
            pygame.draw.line(sc, col(c), (r.left, r.centery), (r.left - 10, r.centery - 6 - wing), 3); pygame.draw.line(sc, col(c), (r.right, r.centery), (r.right + 10, r.centery - 6 - wing), 3)
            pygame.draw.circle(sc, (255, 255, 255), (r.centerx + e.face * 4, r.centery - 2), 4)
            if e.cd < 25: pygame.draw.circle(sc, COLORS["enemy_shot"], r.center, e.w // 2 + 4, 2)
        else:
            tel = e.state == "windup"; cc = mix(c, (230, 60, 60), (1 - e.st / BRUTE["windup"]) if tel else 0)
            if e.state == "recover" and (s.frame // 6) % 2: cc = mix(cc, (255, 240, 120), 0.5)
            pygame.draw.rect(sc, col(cc), r, border_radius=4)
            sx = r.right if e.face > 0 else r.left - 8  # Schild vorne
            pygame.draw.rect(sc, (60, 60, 70), (sx, r.top + 8, 8, r.h - 14), border_radius=3)
            arm_ang = -2.2 if tel else (1.0 if e.state == "strike" else 0.4)
            ax, ay = r.centerx, r.top + 14; ex2 = ax + math.cos(arm_ang) * 34 * e.face; ey2 = ay + math.sin(arm_ang) * 34
            pygame.draw.line(sc, (40, 40, 40), (ax, ay), (ex2, ey2), 6); pygame.draw.circle(sc, (40, 40, 40), (int(ex2), int(ey2)), 9)
            if tel: t = s.font.render("!", True, (220, 30, 30)); sc.blit(t, (r.centerx - 3, r.top - 24))
            if e.state == "strike": pygame.draw.arc(sc, (220, 30, 30), pygame.Rect(r.centerx - 70, r.top - 10, 140, r.h + 20), -1.2 if e.face > 0 else 1.9, 1.2 if e.face > 0 else 4.4, 5)
            if e.state == "recover": t = s.small.render("offen!", True, (160, 120, 0)); sc.blit(t, (r.centerx - t.get_width() / 2, r.top - 18))
        if e.hp < e.maxhp:
            pygame.draw.rect(sc, (60, 60, 60), (r.left, r.top - 8, r.w, 4)); pygame.draw.rect(sc, (220, 60, 60), (r.left, r.top - 8, int(r.w * clamp(e.hp / e.maxhp, 0, 1)), 4))
    def draw_hud(s):
        sc = s.screen; p = s.player; f = clamp(p.hp / PLAYER["hp"], 0, 1)
        pygame.draw.rect(sc, (255, 255, 255), (14, 14, 224, 46), border_radius=6); pygame.draw.rect(sc, (60, 60, 60), (14, 14, 224, 46), 2, border_radius=6)
        sc.blit(s.small.render("HP", True, COLORS["text"]), (22, 20)); pygame.draw.rect(sc, (200, 200, 200), (48, 22, 180, 12))
        pygame.draw.rect(sc, mix((220, 50, 50), (60, 190, 90), f), (48, 22, int(180 * f), 12))
        sc.blit(s.small.render(f"{max(0, int(p.hp))}", True, COLORS["text"]), (200, 20))
        sc.blit(s.small.render("Dash", True, COLORS["text"]), (22, 38)); df = 1 - p.dash_cd / DASH["cooldown"]
        pygame.draw.rect(sc, (200, 200, 200), (60, 42, 80, 8)); pygame.draw.rect(sc, COLORS["teal"] if df >= 1 else (120, 160, 160), (60, 42, int(80 * df), 8))
        if p.charge > 10: pygame.draw.rect(sc, (255, 255, 255) if p.charge >= CHARGED["hold_frames"] else COLORS["teal"], (150, 42, int(80 * clamp(p.charge / CHARGED["hold_frames"], 0, 1)), 8))
        t = s.small.render("Trainingsgelände   H = Hilfe", True, COLORS["text"]); sc.blit(t, (SCREEN_W - t.get_width() - 14, 14))
        if s.show_help:
            lines = ["Steuerung", "A/D, Pfeile: laufen", "Leertaste/W: springen (2x, Wand)", "Shift: Dash", "J/Linksklick: Blaster",
                     "  halten = Ladeschuss", "K/Rechtsklick: Nahkampf (3er-Combo)", "S/Runter + Leertaste: durchfallen",
                     "R: Neustart   H: Hilfe   ESC: Ende", "Brocken: nur von hinten,", "  Nahkampf oder nach Angriff"]
            h = 18 * len(lines) + 12; pygame.draw.rect(sc, (255, 255, 255), (SCREEN_W - 284, 36, 270, h), border_radius=6); pygame.draw.rect(sc, (60, 60, 60), (SCREEN_W - 284, 36, 270, h), 2, border_radius=6)
            for i, l in enumerate(lines): sc.blit((s.font if i == 0 else s.small).render(l, True, COLORS["text"]), (SCREEN_W - 274, 42 + i * 18))
        if s.dead_t: s.center_text("Besiegt!", (200, 40, 40))
        if s.won: s.center_text("Geschafft!", (30, 140, 80), "Leertaste = nochmal")
    def center_text(s, txt, c, sub=None):
        t = s.big.render(txt, True, c); s.screen.blit(t, (SCREEN_W / 2 - t.get_width() / 2, SCREEN_H / 2 - 60))
        if sub: u = s.font.render(sub, True, COLORS["text"]); s.screen.blit(u, (SCREEN_W / 2 - u.get_width() / 2, SCREEN_H / 2 + 4))


# ---------------- Touch-Steuerung (Web/Handy) ----------------
STICK = dict(radius=80, deadzone=0.15, down=0.6)  # schwebender Joystick links
TOUCH_BTNS = {  # Name: (x, y, Radius, Aktion, Label) in Spielkoordinaten 960x540; Trefferflaeche = Radius * hit
    "jump": (880, 460, 62, "jump", "Sprung"), "dash": (750, 480, 50, "dash", "Dash"),
    "shoot": (880, 320, 52, "shoot", "Schuss"), "melee": (755, 360, 50, "melee", "Hieb"),
    "restart": (430, 24, 20, "restart", "R"), "help": (480, 24, 20, "help", "H"),
}
BTN_HIT = 1.35
class TouchInput(Input):
    def __init__(s): super().__init__(); s.fingers = {}; s.touch_seen = False; s.stick_id = None; s.stick_o = None; s.stick_v = (0.0, 0.0)
    def handle(s, ev):
        if ev.type not in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP): return
        x, y = ev.x * SCREEN_W, ev.y * SCREEN_H; fid = ev.finger_id
        if ev.type == pygame.FINGERUP:
            s.fingers.pop(fid, None)
            if fid == s.stick_id: s.stick_id = None; s.stick_o = None; s.stick_v = (0.0, 0.0)
            return
        s.touch_seen = True
        if ev.type == pygame.FINGERDOWN and s.stick_id is None and x < SCREEN_W * 0.5 and y > 60:
            s.stick_id = fid; s.stick_o = (x, y)
        if fid == s.stick_id:
            dx, dy = x - s.stick_o[0], y - s.stick_o[1]; r = STICK["radius"]; d = math.hypot(dx, dy)
            if d > r: dx, dy = dx / d * r, dy / d * r
            s.stick_v = (dx / r, dy / r)
        else: s.fingers[fid] = (x, y)
    def touch_actions(s):
        acts = set()
        for fx, fy in s.fingers.values():
            for name, (bx, by, r, a, _) in TOUCH_BTNS.items():
                if math.hypot(fx - bx, fy - by) < r * BTN_HIT: acts.add(a)
        if s.stick_v[1] > STICK["down"]: acts.add("down")  # nach oben springt NICHT
        return acts
    def poll(s):
        super().poll()
        if s.touch_seen:
            s.cur.discard("shoot"); s.cur.discard("melee")  # Finger erzeugen sonst Maus-Klicks
            keys = pygame.key.get_pressed()
            if keys[pygame.K_j]: s.cur.add("shoot")
            if keys[pygame.K_k]: s.cur.add("melee")
            s.cur |= s.touch_actions()
            vx = s.stick_v[0]; dz = STICK["deadzone"]
            if abs(vx) > dz: s.ax = (vx - math.copysign(dz, vx)) / (1 - dz)
def draw_touch(sc, inp, font):
    if not getattr(inp, "touch_seen", False): return
    ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    o = inp.stick_o or (140, 420); r = STICK["radius"]
    pygame.draw.circle(ov, col((40, 40, 60), 60), o, r); pygame.draw.circle(ov, col((255, 255, 255), 120), o, r, 2)
    k = (o[0] + inp.stick_v[0] * r, o[1] + inp.stick_v[1] * r)
    pygame.draw.circle(ov, col((0, 150, 140), 170 if inp.stick_o else 90), (int(k[0]), int(k[1])), 34)
    for name, (bx, by, br, a, lab) in TOUCH_BTNS.items():
        on = a in inp.cur
        pygame.draw.circle(ov, col((0, 150, 140) if on else (40, 40, 60), 150 if on else 80), (bx, by), br)
        pygame.draw.circle(ov, col((255, 255, 255), 140), (bx, by), br, 2)
        t = font.render(lab, True, (255, 255, 255)); ov.blit(t, (bx - t.get_width() / 2, by - t.get_height() / 2))
    sc.blit(ov, (0, 0))
def is_portrait():
    try:
        import platform as _p
        w = _p.window.innerWidth; h = _p.window.innerHeight
        return h > w
    except Exception:
        return False

async def run():
    pygame.init(); pygame.display.set_caption("Mechanik-Prototyp")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H)); clock = pygame.time.Clock()
    auto = int(os.environ.get("MECH_AUTOTEST", "0"))
    g = Game(screen, RandomInput(int(os.environ.get("MECH_SEED", "1"))) if auto else TouchInput())
    tfont = pygame.font.SysFont("arial", 15, bold=True)
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT: return g
            if hasattr(g.inp, "handle"): g.inp.handle(ev)
        if "quit" in g.inp.cur and not auto and sys.platform != "emscripten": return g
        if getattr(g.inp, "touch_seen", False) and g.frame == 1: pass
        if isinstance(g.inp, TouchInput) and g.inp.touch_seen and g.show_help and not getattr(g, "_hid", False):
            g.show_help = False; g._hid = True  # Hilfe verdeckt sonst Buttons
        # fester Zeitschritt 60 Hz, unabhaengig von 90/120-Hz-Displays
        if auto: steps = 1
        else:
            now = time.perf_counter(); acc = min(getattr(g, "_acc", 0.0) + now - getattr(g, "_last", now), 0.1); g._last = now
            steps = int(acc * FPS); g._acc = acc - steps / FPS
        for _ in range(steps):
            g.inp.poll(); g.update()
        g.draw(); draw_touch(screen, g.inp, tfont)
        if g.frame % 30 == 0: g._portrait = is_portrait()
        if getattr(g, "_portrait", False):
            screen.fill((20, 20, 30)); t = g.big.render("Bitte quer halten", True, (255, 255, 255))
            screen.blit(t, (SCREEN_W / 2 - t.get_width() / 2, SCREEN_H / 2 - 30))
        if auto and g.frame >= auto: return g
        if auto and g.frame % 900 == 0 and g.player.hp > 40: g.hurt_player(999, 1)
        pygame.display.flip()
        if not auto: clock.tick(FPS)
        await asyncio.sleep(0)

async def main():
    try:
        g = await run()
        if os.environ.get("MECH_AUTOTEST"): print("STATS", g.frame, g.stats)
    except Exception:
        traceback.print_exc()
        try:
            with open(os.path.join(BASE, "crash.log"), "w", encoding="utf-8") as f: f.write(traceback.format_exc())
        except Exception: pass
    if sys.platform != "emscripten": pygame.quit()

asyncio.run(main())
