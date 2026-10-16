"""Left marble board on pymunk.

Bodies: rotating kinematic hexagon peg clusters, rounded cup walls, a value gate (buffer strip),
rounded item-slot dividers. Cups and item slots are sensors, so a marble triggers them on entry
and is consumed or teleported at once (fix: marbles bouncing back out without triggering)."""
import math
import pymunk
from .config import (LEFT, H, GRAV, PEG_R, GAP, BUOY_Y0, CUP_FLOOR, LPILLARS, SLOT_X, SLOT_TOP, MULT,
                     CLUSTERS, CLUSTER_R, ITEM_X, IPILLARS, ITEM_TOP, ITEM_FLOOR, GATE_VALUE,
                     marble_radius, clamp)

MARBLE, CUP, GATE, ITEM, WALL = 1, 2, 3, 4, 5
EMIT = (LEFT / 2, 96.0)          # top-centre spout (ref2: ~13% of board height)
E_EACH = math.sqrt(.6)          # pymunk multiplies elasticities: marble x wall = 0.6
VMAX = 520.0


class Marble:
    __slots__ = ('team', 'v', 'r', 'body', 'shape', 'wait', 'trail', 'still', 'passing', 'zone', 'uid', 'age', 'queued')

    def __init__(self, team, v, uid):
        self.team, self.v, self.uid = team, v, uid
        self.r = marble_radius(v)
        self.body = self.shape = None
        self.wait = 0.0
        self.trail = []
        self.still = 0.0
        self.passing = False
        self.zone = 0
        self.age = 0.0
        self.queued = False


def _vel_cap(body, gravity, damping, dt):
    pymunk.Body.update_velocity(body, gravity, damping, dt)
    vx, vy = body.velocity
    s = math.hypot(vx, vy)
    if s > VMAX:
        body.velocity = (vx * VMAX / s, vy * VMAX / s)


class Board:
    def __init__(self, sim):
        self.sim = sim
        self.rng = sim.rng
        sp = self.space = pymunk.Space()
        sp.gravity = (0, GRAV)
        sp.iterations = 20
        sp.collision_slop = .2
        st = sp.static_body
        shapes = []

        def seg(a, b, r, ctype=WALL):
            s = pymunk.Segment(st, a, b, r)
            s.elasticity = E_EACH; s.friction = 1.0; s.collision_type = ctype
            shapes.append(s); return s
        # outer walls
        seg((0, -200), (0, H), 1); seg((LEFT, -200), (LEFT, H), 1); seg((0, 0), (LEFT, 0), 2); seg((0, ITEM_FLOOR + 2), (LEFT, ITEM_FLOOR + 2), 2)
        # cup row: rounded pillars (segment radius = half width → round caps, nothing can balance on top)
        self.pillars = []
        for x, w, top in LPILLARS:
            for xx in (x, LEFT - x - w):
                r = max(3.0, w / 2)
                cx = xx + w / 2
                seg((cx, top + r), (cx, CUP_FLOOR), r)
                self.pillars.append((xx, w, top))
        seg((0, CUP_FLOOR), (GAP[0], CUP_FLOOR), 2); seg((GAP[1], CUP_FLOOR), (LEFT, CUP_FLOOR), 2)
        # cup sensors: entering the cup mouth = landed
        for x0, x1, slot in SLOT_X:
            s = pymunk.Poly(st, [(x0, SLOT_TOP[slot] + 6), (x1, SLOT_TOP[slot] + 6), (x1, CUP_FLOOR), (x0, CUP_FLOOR)])
            s.sensor = True; s.collision_type = CUP; s.slot = slot; shapes.append(s)
        # buffer strip / value gate: slightly crowned
        cx = (GAP[0] + GAP[1]) / 2
        self.gate = [seg((GAP[0] + 2, BUOY_Y0 + 4), (cx, BUOY_Y0), 2, GATE), seg((cx, BUOY_Y0), (GAP[1] - 2, BUOY_Y0 + 4), 2, GATE)]
        # item-slot dividers: rounded caps (fix: marbles parked on flat divider tops)
        for x, w in IPILLARS:
            r = w / 2
            seg((x + r, ITEM_TOP + r), (x + r, ITEM_FLOOR), r)
        for k in range(5):
            x0, x1 = ITEM_X[k] + 6, ITEM_X[k + 1] - 6
            s = pymunk.Poly(st, [(x0, ITEM_TOP + 18), (x1, ITEM_TOP + 18), (x1, ITEM_FLOOR), (x0, ITEM_FLOOR)])
            s.sensor = True; s.collision_type = ITEM; s.slot = k; shapes.append(s)
        sp.add(*shapes)
        # rotating hexagon peg clusters (kinematic: contact uses true surface velocity)
        self.clusters = []
        for i, (cx, cy, w) in enumerate(CLUSTERS):
            b = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            b.position = (cx, cy); b.angle = i * .5; b.angular_velocity = w
            ps = [pymunk.Circle(b, PEG_R, (0, 0))] + [pymunk.Circle(b, PEG_R, (math.cos(k * math.pi / 3) * CLUSTER_R, math.sin(k * math.pi / 3) * CLUSTER_R)) for k in range(6)]
            for p in ps:
                p.elasticity = E_EACH; p.friction = 1.0; p.collision_type = WALL
            sp.add(b, *ps)
            self.clusters.append(b)
        sp.on_collision(MARBLE, CUP, begin=self._cup)
        sp.on_collision(MARBLE, ITEM, begin=self._item)
        sp.on_collision(MARBLE, GATE, pre_solve=self._gate)
        self.marbles = []
        self.queue = []
        self.uid = 0
        self.hit = [0] * 8
        self.slot_flash = [0.0] * 8
        self.item_flash = [None] * 5
        self.gate_pass = 0
        self.next_marble = [v * sim.k for v in (.15, .35, .55, .8)]
        self.fx = []                     # visual events for the renderer (consumed marbles, cup hits)
        self.queue_launch = []           # marbles waiting inside the top emitter (not in the physics space)
        self.emit_clock = .5 * sim.k     # first launch at 0.5 reference seconds
        self.side = 1
        order = [0, 1, 2, 3] * 4
        for i in range(16):              # opening: a stream of small mixed-colour marbles (values 1-8)
            self.add_marble(order[i], 2 ** int(self.rng.integers(0, 4)))

    # -- marbles -------------------------------------------------------------
    def add_marble(self, team, v):
        m = Marble(team, v, self.uid); self.uid += 1
        self._make_body(m)
        self.marbles.append(m)
        self._enqueue(m)
        return m

    def _enqueue(self, m):
        """Park the marble in the top emitter; it is lobbed out when its turn comes."""
        if m.body in self.space.bodies:
            self.space.remove(m.body, m.shape)
        m.queued = True
        m.body.position = EMIT
        m.body.velocity = (0, 0)
        m.trail = []; m.still = 0.0; m.passing = False; m.zone = 0
        self.queue_launch.append(m)

    def _launch(self, m):
        """ref2 emitter: one spout at the top centre, marbles lobbed up-and-out, alternating left / right."""
        rng = self.rng
        side = self.side; self.side = -self.side
        vx = side * rng.uniform(40, 215)
        vy = -rng.uniform(120, 215)
        m.body.position = (EMIT[0] + side * 4, EMIT[1])
        m.body.velocity = (vx, vy)
        m.queued = False
        self.space.add(m.body, m.shape)

    def _make_body(self, m, pos=None, vel=None):
        if m.body is not None:
            pos, vel = m.body.position, m.body.velocity
            if m.body in self.space.bodies:
                self.space.remove(m.body, m.shape)
        mass = m.r * m.r * .01
        b = pymunk.Body(mass, pymunk.moment_for_circle(mass, 0, m.r))
        b.velocity_func = _vel_cap
        s = pymunk.Circle(b, m.r)
        s.elasticity = E_EACH; s.friction = .08; s.collision_type = MARBLE; s.marble = m
        if pos is not None:
            b.position = pos; b.velocity = vel
        m.body, m.shape = b, s
        self.space.add(b, s)

    def _cup(self, arb, space, data):
        m = arb.shapes[0].marble
        if m.zone == 0 and not m.passing:
            self.queue.append(('cup', m, arb.shapes[1].slot))

    def _item(self, arb, space, data):
        m = arb.shapes[0].marble
        self.queue.append(('item', m, arb.shapes[1].slot))

    def _gate(self, arb, space, data):
        m = arb.shapes[0].marble
        if m.v >= GATE_VALUE or m.passing:
            arb.process_collision = False
            if not m.passing:
                m.passing = True; self.gate_pass += 1
                m.body.velocity = (self.rng.uniform(-280, 280), max(60.0, m.body.velocity[1]))
        else:
            self.queue.append(('boost', m, 0))

    def _consume(self, m):
        if m in self.marbles:
            self.marbles.remove(m)
            if m.body in self.space.bodies:
                self.space.remove(m.body, m.shape)
            if m in self.queue_launch:
                self.queue_launch.remove(m)

    def tick(self, dt):
        sim, rng = self.sim, self.rng
        r0 = int(sim.frame) % 4                     # rotating start team: no team gets first pick of a free slot
        # Drop marbles whose team is already eliminated (prevents left-slot flash with no right effect).
        for m in list(self.marbles):
            if sim.dead[m.team]:
                self._consume(m)
        for tt in range(4):
            t = (r0 + tt) % 4
            self.next_marble[t] -= dt
            if sim.dead[t]:
                continue
            if self.next_marble[t] <= 0 and sum(1 for q in self.marbles if q.team == t) < 2 and len(self.marbles) < min(8, round(6 / sim.k)):   # per-team + total cap
                k = min(12, int(rng.uniform(0, 3) + min(7, sim.tp / 60) * rng.uniform(.4, .9)))
                self.add_marble(t, 2 ** k)
                self.next_marble[t] = rng.uniform(1.75, 3.9) * clamp(1.4 - sim.tp / 600, .6, 1.4) * sim.k
        for i in range(len(self.slot_flash)):
            self.slot_flash[i] = max(0.0, self.slot_flash[i] - dt * 1.5)
        self.emit_clock -= dt
        if self.queue_launch and self.emit_clock <= 0:
            self._launch(self.queue_launch.pop(0))
            self.emit_clock = (.14 if sim.tp < 4 else .22) * sim.k
        self.queue.clear()
        sub = 4
        for _ in range(sub):
            self.space.step(dt / sub)
        done = set()
        for kind, m, slot in self.queue:
            if m.uid in done or m not in self.marbles or m.queued:
                continue
            if kind == 'boost':
                vx, vy = m.body.velocity
                if vy > -200:
                    m.body.velocity = (vx * .9 + (1 if m.body.position.x > (GAP[0] + GAP[1]) / 2 else -1) * 30, -220 - rng.uniform(0, 120))
                continue
            done.add(m.uid)
            if kind == 'cup':
                self._land_cup(m, slot)
            elif kind == 'item':
                # Physical slot k maps 1:1 to ITEM_NAMES[k]. Do NOT remap via ITEM_MIX
                # (that made the left label disagree with the granted item).
                it = int(slot)
                assert 0 <= it <= 4, it
                x, y = m.body.position
                fired = False
                if not sim.dead[m.team]:
                    # Slot landings are direct triggers, independent of the stored inventory.
                    strength = m.v if it == 3 else None
                    fired = bool(sim.fire_item(m.team, it, strength=strength))
                # Only flash / "+1" when the right-side effect actually fired (no fake UI for dead teams).
                if fired:
                    self.fx.append(('item', x, y, m.team, it, sim.t))
                    self.item_flash[it] = (m.team, sim.t)
                sim.events.append((sim.t, 'item_land', m.team, it, fired))
                self._consume(m)
        # stuck detection + nudge, trails, zone bookkeeping
        for m in list(self.marbles):
            if m.queued:
                continue
            x, y = m.body.position
            vx, vy = m.body.velocity
            m.age += dt
            m.trail.append((x, y))
            if len(m.trail) > 16:
                m.trail.pop(0)
            if y > BUOY_Y0 + 30:
                m.zone = 1
            if m.passing and y < BUOY_Y0 - 40:
                m.passing = False                      # bounced back up above the strip
            if m.zone == 0 and (x < GAP[0] or x > GAP[1]):
                # polled cup check (sensor begin can be missed if the marble entered while flagged as passing)
                for x0, x1, slot in SLOT_X:
                    if x0 <= x < x1 and y + m.r > SLOT_TOP[slot] + 6:
                        self._land_cup(m, slot)
                        break
                if m.trail == []:
                    continue
            sp = math.hypot(vx, vy)
            m.still = m.still + dt if sp < 18 else 0.0
            if m.still > .5:
                if m.zone == 0 and y > 330 and (x < GAP[0] or x > GAP[1]):
                    # resting across a cup mouth: count the nearest cup
                    best = min(SLOT_X, key=lambda z: abs((z[0] + z[1]) / 2 - x))
                    self._land_cup(m, best[2])
                else:
                    m.body.velocity = (rng.choice([-1, 1]) * rng.uniform(70, 120), -rng.uniform(90, 150))
                    m.still = 0.0
            if y > H + 40 or x < -40 or x > LEFT + 40:
                self._consume(m)

    def _land_cup(self, m, slot):
        sim = self.sim
        if m not in self.marbles or m.queued or sim.dead[m.team]:
            if m in self.marbles and not m.queued and sim.dead[m.team]:
                self._consume(m)
            return
        self.hit[slot] += 1
        self.slot_flash[slot] = 1.0
        sim.award(m.team, slot, m.v)
        x, y = m.body.position
        self.fx.append(('cup', x, y, m.team, slot, sim.t))
        m.v = min(m.v * MULT[slot], 2 ** 34)       # multiplier cup: value x X (stacks), relaunch from top centre
        m.r = marble_radius(m.v)
        self._make_body(m)
        self._enqueue(m)                       # re-enters through the same top emitter

    def cluster_pegs(self):
        out = []
        for b in self.clusters:
            cx, cy = b.position
            out.append((cx, cy))
            for k in range(6):
                a = b.angle + k * math.pi / 3
                out.append((cx + math.cos(a) * CLUSTER_R, cy + math.sin(a) * CLUSTER_R))
        return out
