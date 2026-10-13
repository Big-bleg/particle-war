(() => {
  'use strict';

  const W = 1920, H = 1080, LEFT = 760, G = 1000, AX = 860, AY = 40, GS = 168, S = G / GS;
  const PX = 0, PW = 760, BAND = 430, ITEMY = 928, ITEMH = 124;
  // 1:1 ref layout (measured from douyin_detail frames, 1920x1080 space)
  const LEDGE_TOP = 430, LEDGE_BOT = 540, LGROUP = [[0, 222], [538, 760]], GAP = [222, 538];
  const SLOT_X = [[2, 76, 0], [76, 148, 1], [148, 222, 2], [538, 612, 3], [612, 684, 4], [684, 758, 5]]; // x0,x1,slot
  const ITEM_X = [0, 138, 290, 448, 601, 760];
  const MULT = [8, 4, 2, 2, 4, 8], NAMES = ['风暴', '机枪', '护盾', '大球', '狙击'];
  const TEAMS = [
    { name: '红队', c: [255, 20, 70], hi: [255, 90, 130], glow: [255, 40, 90], edge: [255, 200, 220], hex: 0xff1446 },
    { name: '绿队', c: [0, 230, 140], hi: [80, 255, 200], glow: [0, 255, 170], edge: [160, 255, 220], hex: 0x00e68c },
    { name: '蓝队', c: [0, 140, 255], hi: [70, 210, 255], glow: [40, 170, 255], edge: [160, 220, 255], hex: 0x008cff },
    { name: '橙队', c: [255, 165, 20], hi: [255, 220, 80], glow: [255, 185, 40], edge: [255, 240, 180], hex: 0xffa514 }
  ];
  const NEUTRAL = 4, BASES = [[120, 120], [880, 120], [120, 880], [880, 880]], MATCH = 960;
  const MAX_SHOTS = 3500, SILK_CAP = 7000, RIBBON_CAP = 1800;
  const TRES = GS * 2; // 2x upload with domain-warped sampling → organic foam

  const canvas = document.getElementById('game');
  const overlay = document.getElementById('overlay');
  const startpanel = document.getElementById('startpanel');
  const endpanel = document.getElementById('endpanel');

  const rgb = (a, al) => al == null ? `rgb(${a[0] | 0},${a[1] | 0},${a[2] | 0})` : `rgba(${a[0] | 0},${a[1] | 0},${a[2] | 0},${al})`;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const rand = (a, b) => a + Math.random() * (b - a);
  const pick = a => a[(Math.random() * a.length) | 0];
  function fmt(v) {
    v = Math.max(0, +v || 0);
    if (v >= 1e6) { const n = v / 1e6; return (n >= 100 ? n.toFixed(0) : n.toFixed(2)).replace(/\.?0+$/, '') + 'M'; }
    if (v >= 1e3) { const n = v / 1e3; return (n >= 100 ? n.toFixed(0) : n.toFixed(1)).replace(/\.0$/, '') + 'K'; }
    return Math.round(v).toLocaleString('en-US');
  }
  function fmtScore(v) { return Math.max(0, Math.round(+v || 0)).toLocaleString('en-US'); }
  function rr(c, x, y, w, h, r, fill, stroke, lw = 1) {
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
    if (fill) { c.fillStyle = fill; c.fill(); }
    if (stroke) { c.strokeStyle = stroke; c.lineWidth = lw; c.stroke(); }
  }
  function nnoise(x, y) { return (Math.sin(x * 1.73 + y * .41) + Math.sin(y * 1.31 - x * .63) + Math.sin((x + y) * .91) * .55) / 2.55; }

  function bakeGlow(size, stops) {
    const cv = document.createElement('canvas'); cv.width = cv.height = size;
    const g = cv.getContext('2d'), R = size / 2, grd = g.createRadialGradient(R, R, 0, R, R, R);
    for (const [t, col] of stops) grd.addColorStop(t, col);
    g.fillStyle = grd; g.fillRect(0, 0, size, size); return cv;
  }
  function bakeSilk(w, h) {
    const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
    const g = cv.getContext('2d');
    const grd = g.createLinearGradient(0, 0, w, 0);
    grd.addColorStop(0, 'rgba(255,255,255,0)');
    grd.addColorStop(0.35, 'rgba(255,255,255,0.55)');
    grd.addColorStop(0.5, 'rgba(255,255,255,1)');
    grd.addColorStop(0.65, 'rgba(255,255,255,0.55)');
    grd.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grd;
    // soft vertical falloff
    g.globalCompositeOperation = 'source-over';
    g.fillRect(0, 0, w, h);
    const mask = g.createLinearGradient(0, 0, 0, h);
    mask.addColorStop(0, 'rgba(0,0,0,1)');
    mask.addColorStop(0.5, 'rgba(0,0,0,0)');
    mask.addColorStop(1, 'rgba(0,0,0,1)');
    g.globalCompositeOperation = 'destination-out';
    g.fillStyle = mask; g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = 'source-over';
    return cv;
  }

  const SPR2D = {
    whiteSoft: bakeGlow(64, [[0, 'rgba(255,255,255,1)'], [.25, 'rgba(255,255,255,.55)'], [.55, 'rgba(200,230,255,.18)'], [1, 'rgba(0,0,0,0)']]),
    whiteCore: bakeGlow(24, [[0, '#fff'], [.35, 'rgba(255,255,255,.85)'], [1, 'rgba(255,255,255,0)']]),
    spark: bakeGlow(20, [[0, '#fff'], [.4, 'rgba(255,255,220,.7)'], [1, 'rgba(255,200,100,0)']]),
    team: TEAMS.map(t => bakeGlow(96, [[0, rgb(t.hi, 1)], [.2, rgb(t.c, .85)], [.5, rgb(t.glow, .35)], [1, rgb(t.glow, 0)]]))
  };

  /* ===================== SIMULATION ===================== */
  class Game {
    constructor(player) {
      this.player = player; this.t = 0; this.paused = false; this.over = false; this.winner = -1;
      this.autoAim = true; this.firing = false; this.autoFire = true;
      this.grid = new Uint8Array(GS * GS).fill(NEUTRAL); this.claimRadius = 14; this.expandClock = 0;
      this.share = [0, 0, 0, 0]; this.level = [0, 0, 0, 0];
      this.ammo = [25.06e6, 25.02e6, 24.84e6, 25.12e6];
      this.score = [198000, 296000, 220000, 299000]; this.shield = [1, 1, 1, 1];
      this.items = [0, 0, 0, 0, 0]; this.aiItems = Array.from({ length: 4 }, () => [0, 0, 0, 0, 0]);
      this.hit = [0, 0, 0, 0, 0, 0]; this.slotFlash = []; this.itemFlash = [];
      this.marbles = []; this.nextMarble = [.15, .35, .55, .8]; this.cool = [0, 0, 0, 0];
      this.aim = BASES.map(([x, y]) => Math.atan2(G / 2 - y, G / 2 - x));
      this.playerAim = this.aim[player];
      this.shots = []; this.sparks = []; this.frontierSparks = [];
      this.heat = new Float32Array(GS * GS); this.waves = []; this.heatClock = 0; this.lastStorm = [];
      // asymmetric momentum: each team has a drifting fire-power multiplier
      this.power = [0, 1, 2, 3].map(() => rand(.8, 1.25)); this.powerClock = 0;
      this.sweepPh = [0, 1, 2, 3].map(() => rand(0, 6.28)); this.sweepSp = [0, 1, 2, 3].map(() => rand(.15, .4));
      this.events = []; this.lock = [null, null, null, null]; this.spin = [0, 1, 2, 3].map(t => (t % 2 ? -1 : 1) * rand(.45, .7));
      this.ribbons = []; this.silk = new Float32Array(SILK_CAP * 7); this.silkCount = 0;
      this.stars = Array.from({ length: 220 }, () => [rand(0, G), rand(0, G), rand(.2, 1), rand(.5, 2.2)]);
      this.frame = 0; this.dirty = true; this.terrainAge = 0;
      this.pegs = this.makePegs(); this.lowerPegs = this.makeLowerPegs();
      this.fpsEMA = 60; this._lastNow = 0;

      for (let i = 0; i < 16; i++) { this.marble(i % 4); const m = this.marbles[this.marbles.length - 1]; m.x = 130 + i * 27 + rand(-4, 4); m.y = 24 + rand(-3, 3); m.wait = .8 + i * .15; m.v = 32; m.r = 6.5; m.path = [[m.x, m.y]]; }
      // seed silk immediately so t~10s looks dense

    }
    id(x, y) { return y * GS + x; }
    scatter(n, y0, y1) {
      const a = [];
      let tries = 0;
      while (a.length < n && tries++ < 4000) {
        const x = rand(40, LEFT - 40), y = rand(y0, y1);
        if (a.every(q => (q[0] - x) ** 2 + (q[1] - y) ** 2 > 95 * 95)) a.push([x, y, rand(-3, 3), rand(-2, 2), y0, y1]);
      }
      return a;
    }
    lattice(rows) {
      const a = [];
      rows.forEach((y, i) => { const n = i % 2 ? 4 : 3, step = (LEFT - 120) / n; for (let k = 0; k < n; k++) { const yy = y + rand(-22, 22); a.push([60 + step * (k + .5) + rand(-40, 40), yy, rand(-2, 2), rand(-1, 1), yy - 18, yy + 18]); } });
      return a;
    }
    makePegs() { return this.lattice([105, 190, 275, 360]); }
    makeLowerPegs() { return this.lattice([590, 680, 770, 860]); }
    // cellular smoothing: rounds bullet spikes into foamy blobs/tongues (no radial auto-expand)
    smoothFront() {
      const g = this.grid, out = g.slice(), c = [0, 0, 0, 0, 0];
      for (let y = 1; y < GS - 1; y++) for (let x = 1; x < GS - 1; x++) {
        const i = y * GS + x, t = g[i];
        c[0] = c[1] = c[2] = c[3] = c[4] = 0;
        c[g[i - 1]]++; c[g[i + 1]]++; c[g[i - GS]]++; c[g[i + GS]]++;
        c[g[i - GS - 1]]++; c[g[i - GS + 1]]++; c[g[i + GS - 1]]++; c[g[i + GS + 1]]++;
        let bt = 0; for (let k = 1; k < 4; k++) if (c[k] > c[bt]) bt = k;
        if (t === NEUTRAL) { if (c[bt] >= 6 && Math.random() < .5) out[i] = bt; }
        else if (c[t] <= 2) { out[i] = c[bt] >= 4 ? bt : (c[4] >= 5 ? NEUTRAL : t); }
      }
      this.grid = out; this.dirty = true;
    }
    growBases(rc) {
      for (let t = 0; t < 4; t++) {
        const cx = BASES[t][0] / S, cy = BASES[t][1] / S, R0 = Math.ceil(rc * 1.3);
        for (let y = Math.max(0, (cy - R0) | 0); y < Math.min(GS, cy + R0); y++) for (let x = Math.max(0, (cx - R0) | 0); x < Math.min(GS, cx + R0); x++) {
          const i = y * GS + x; if (this.grid[i] !== NEUTRAL) continue;
          const dx = x - cx, dy = y - cy, a = Math.atan2(dy, dx), r = rc * (1 + .2 * Math.sin(a * 5 + t * 1.7) + .14 * nnoise(x * .5, y * .5));
          if (dx * dx + dy * dy < r * r) { this.grid[i] = t; this.heat[i] = 1; }
        }
      }
      this.dirty = true;
    }
    seedBases(rc) {
      for (let t = 0; t < 4; t++) {
        const cx = BASES[t][0] / S, cy = BASES[t][1] / S;
        for (let y = 0; y < GS; y++) for (let x = 0; x < GS; x++) {
          const dx = x - cx, dy = y - cy, a = Math.atan2(dy, dx);
          const r = rc * (1 + .18 * Math.sin(a * 5 + t) + .1 * nnoise(x * .9, y * .9));
          if (dx * dx + dy * dy < r * r) this.grid[y * GS + x] = t;
        }
      }
      this.dirty = true;
    }
    expandTo(radius) {
      this.claimRadius = radius; const r2 = radius * radius;
      for (let y = 0; y < GS; y++) for (let x = 0; x < GS; x++) {
        const i = this.id(x, y); if (this.grid[i] !== NEUTRAL) continue;
        let best = 1e9, bt = -1;
        for (let t = 0; t < 4; t++) {
          const [bx, by] = BASES[t], dx = x - bx / S, dy = y - by / S, d = dx * dx + dy * dy;
          if (d < best) { best = d; bt = t; }
        }
        const jitter = nnoise(x * 1.1, y * 1.1) * 22 + nnoise(x * .37, y * .51) * 16 + nnoise(x * 2.7, y * 2.1) * 10;
        // lobe warping makes frontiers tongue-shaped like ref nebulae
        const ang = Math.atan2(y - BASES[bt][1] / S, x - BASES[bt][0] / S);
        const lobe = 1 + 0.22 * Math.sin(ang * 3 + bt) + 0.12 * Math.sin(ang * 5 - bt * 1.3);
        if (best < (r2 * lobe * lobe) + jitter * radius * .85) this.grid[i] = bt;
      }
      this.dirty = true;
    }
    marble(team) {
      // values double: early 16–256, grows to K / M (ref: 64 → 131K → 1M)
      const k = Math.min(20, Math.floor(rand(4, 8) + Math.min(16, this.t / 5) * rand(.6, 1)));
      const v = Math.pow(2, k);
      const ang = Math.PI / 2 + rand(-.75, .75), sp = rand(150, 240);
      const r = .85 * (v >= 1e6 ? 25 : v >= 1e5 ? 20 : v >= 5e4 ? 18 : v >= 2e4 ? 16.5 : v >= 1e4 ? 15 : v >= 1e3 ? 13 : v >= 100 ? 10 : 8.5);
      this.marbles.push({ team, x: rand(60, LEFT - 60), y: 22, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, v, r, hit: -1, trail: [], path: [[0, 0]], zone: 0 }); { const mm = this.marbles[this.marbles.length - 1]; mm.path[0] = [mm.x, mm.y]; }
    }
    award(team, slot, value) {
      const v = value * MULT[slot];
      this.score[team] += v; this.ammo[team] = Math.min(999e6, this.ammo[team] + v * .004 * (1 + this.t / 90));
      this.slotFlash[slot] = { team, life: 1 };
    }
    spawn(team, kind = 0, count = null, angle = null) {
      if (this.ammo[team] < 800 || this.shots.length >= MAX_SHOTS) return;
      const [bx, by] = BASES[team], baseAng = angle ?? this.aim[team];
      const age = this.t / MATCH;
      if (kind === 0) kind = age < .12 ? 0 : age < .45 ? 1 : age < .75 ? 1 : 4;
      let n = count ?? (kind === 0 ? 8 : kind === 1 ? 10 : kind === 4 ? 12 : 1);
      if (kind === 2) n = 1; if (kind === 3) n = count ?? 7;
      const speed = kind === 2 ? 2.2 : kind === 3 ? 15 : kind === 4 ? 8.2 : kind === 1 ? 9.5 : 7.4;
      const spread = kind === 2 ? 0 : kind === 3 ? .02 : kind === 4 ? .07 : kind === 1 ? .07 : .075;
      const cost = kind === 2 ? 220e3 : kind === 3 ? 28e3 : Math.max(200, n * 260);
      this.ammo[team] = Math.max(0, this.ammo[team] - cost);
      for (let k = 0; k < n && this.shots.length < MAX_SHOTS; k++) {
        const a = baseAng + (k - (n - 1) / 2) * spread + rand(-.02, .02);
        const v = rand(speed * .9, speed * 1.12);
        this.shots.push({
          team, x: bx + Math.cos(a) * 10, y: by + Math.sin(a) * 10,
          vx: Math.cos(a) * v, vy: Math.sin(a) * v, kind, life: 0,
          value: kind === 2 ? 14e6 * (1 + age * 10) : kind === 3 ? 220e3 : 14e3,
          trail: []
        });
      }
    }
    use(team, i) {
      const bag = team === this.player ? this.items : this.aiItems[team];
      if (bag[i] <= 0 || (i === 3 && this.t < 45)) return false; bag[i]--;
      const a = this.aim[team];
      if (i === 0 && (this.t < 120 || this.waves.some(w => w.team === team) || this.t - (this.lastStorm[team] || -99) < 35)) { for (let k = 0; k < 30; k++) this.spawn(team, 1, 1, a + (k - 14.5) * .05); }
      else if (i === 0) { this.lastStorm[team] = this.t; this.waves.push({ team, r: 70, a: a, half: .55 + Math.min(.35, this.t / 600), sp: 150 + this.t * .4, life: 0 }); this.events.push({ t: this.t, team, kind: 'storm' }); }
      if (i === 1) { for (let k = 0; k < 14; k++) this.spawn(team, 0, 3, a + rand(-.28, .28)); }
      if (i === 2) { this.shield[team] = 1; this.sparks.push({ x: BASES[team][0], y: BASES[team][1], team, life: 1, burst: true }); }
      if (i === 3 && this.shots.filter(q => q.kind === 2).length >= 3) { bag[i]++; return false; }
      if (i === 3) { this.ammo[team] += 2e5; this.spawn(team, 2, 1, a); const s2 = this.shots[this.shots.length - 1]; if (s2 && s2.kind === 2) s2.value = rand(3e5, 1.2e6) * (1 + this.t / 500); this.events.push({ t: this.t, team, kind: 'bigball' }); }
      if (i === 4) this.spawn(team, 3, 6, a);
      return true;
    }
    paint(x, y, team, r) {
      const gx = Math.round(x / S), gy = Math.round(y / S), gr = Math.max(1, Math.ceil(r / S));
      for (let dy = -gr; dy <= gr; dy++) for (let dx = -gr; dx <= gr; dx++) {
        if (dx * dx + dy * dy > gr * gr * (.55 + Math.random() * .7)) continue;
        const xx = gx + dx, yy = gy + dy; if (xx < 0 || yy < 0 || xx >= GS || yy >= GS) continue;
        const i = this.id(xx, yy);
        if (this.grid[i] !== team) { this.grid[i] = team; this.score[team] = Math.max(0, this.score[team] + 35); this.dirty = true; }
        this.heat[i] = 1;
      }
    }
    hitShot(p) {
      const gx = Math.floor(p.x / S), gy = Math.floor(p.y / S);
      if (gx < 0 || gy < 0 || gx >= GS || gy >= GS) return true;
      const owner = this.grid[this.id(gx, gy)];
      if (owner === p.team) return false;
      if (owner < 4 && this.shield[owner] > .02) {
        const [bx, by] = BASES[owner];
        if (Math.hypot(p.x - bx, p.y - by) < 100) {
          this.shield[owner] = Math.max(0, this.shield[owner] - (p.kind === 2 ? .07 : .0025));
          this.sparks.push({ x: p.x, y: p.y, team: owner, life: .7 });
          return true;
        }
      }
      const radius = p.kind === 2 ? 42 : p.kind === 3 ? 14 : p.kind === 1 ? 8 : p.kind === 4 ? 6 : 5.5;
      this.paint(p.x, p.y, p.team, radius * (1 + Math.min(1.2, this.t / 200)) * (this.t < 70 ? .5 + .5 * this.t / 70 : 1));
      if (Math.random() < .35) this.sparks.push({ x: p.x, y: p.y, team: p.team, life: .55 + Math.random() * .3 });
      if (p.kind === 2) { p.value *= .995; p.life++; p.v0 = p.v0 || p.value; return p.life > 260 || p.value < p.v0 * .3; }
      return true;
    }
    pushSilk(team, x, y, vx, vy, life) {
      if (this.silkCount >= SILK_CAP) {
        // overwrite random older slot (keeps density without GC)
        const i = ((Math.random() * SILK_CAP) | 0) * 7;
        this.silk[i] = x; this.silk[i + 1] = y; this.silk[i + 2] = vx; this.silk[i + 3] = vy;
        this.silk[i + 4] = life; this.silk[i + 5] = team; this.silk[i + 6] = Math.atan2(vy, vx);
        return;
      }
      const i = this.silkCount * 7;
      this.silk[i] = x; this.silk[i + 1] = y; this.silk[i + 2] = vx; this.silk[i + 3] = vy;
      this.silk[i + 4] = life; this.silk[i + 5] = team; this.silk[i + 6] = Math.atan2(vy, vx);
      this.silkCount++;
    }
    pushSilkSeed() {
      const t = (Math.random() * 4) | 0;
      const [bx, by] = BASES[t], a = this.aim[t] + rand(-.45, .45), sp = rand(6, 18);
      const dist = rand(20, 380);
      this.pushSilk(t, bx + Math.cos(a) * dist, by + Math.sin(a) * dist, Math.cos(a) * sp, Math.sin(a) * sp, .4 + Math.random() * .9);
    }
    giveItem(team, type) {
      if (team === this.player) this.items[type] = Math.min(99, this.items[type] + 1);
      else this.aiItems[team][type] = Math.min(99, this.aiItems[team][type] + 1);
      if (type === 2) this.shield[team] = Math.min(1, this.shield[team] + .08);
      this.itemFlash[type] = { team, life: 1 };
    }
    tickMarbles(dt) {
      for (let t = 0; t < 4; t++) {
        this.nextMarble[t] -= dt;
        if (this.nextMarble[t] <= 0 && this.marbles.length < 20) { this.marble(t); this.nextMarble[t] = rand(.6, 1.5) * clamp(1.4 - this.t / 600, .6, 1.4); }
      }
      if (this.marbles.length > 18) this.marbles = this.marbles.filter(m => m.wait > 0 || (m.age = (m.age || 0) + dt) < 16);
      for (const P of [this.pegs, this.lowerPegs]) for (const q of P) {
        q[0] += q[2] * dt; q[1] += q[3] * dt;
        if (q[0] < 40 || q[0] > LEFT - 40) q[2] *= -1;
        if (q[1] < q[4] || q[1] > q[5]) q[3] *= -1;
      }
      for (const f of this.slotFlash) if (f) f.life -= dt * 1.5;
      for (const f of this.itemFlash) if (f) f.life -= dt * 1.5;
      const live = [];
      for (const m of this.marbles) {
        if (m.wait > 0) { m.wait -= dt; live.push(m); continue; }
        if (m.lift) {
          m.trail.push([m.x, m.y]); if (m.trail.length > 9) m.trail.shift();
          m.vx += ((LEFT / 2 + m.lx) - m.x) * 1.6 * dt - m.vx * 1.2 * dt; m.vy = Math.max(-300, m.vy - 140 * dt);
          m.x += m.vx * dt; m.y += m.vy * dt;
          if (m.y > 60) live.push(m);
          continue;
        }
        m.trail.push([m.x, m.y]); if (m.trail.length > 9) m.trail.shift();
        m.vy += 55 * dt;
        const spd = Math.hypot(m.vx, m.vy); if (spd > 320) { m.vx *= 320 / spd; m.vy *= 320 / spd; }
        m.x += m.vx * dt; m.y += m.vy * dt;
        const pr = m.zone ? this.lowerPegs : this.pegs;
        for (const q of pr) {
          const dx = m.x - q[0], dy = m.y - q[1], rr = m.r + 6;
          if (dx * dx + dy * dy < rr * rr) {
            const d = Math.hypot(dx, dy) || 1, nx = dx / d, ny = dy / d, dot = m.vx * nx + m.vy * ny;
            if (dot < 0) { m.vx -= 1.9 * dot * nx; m.vy -= 1.9 * dot * ny; }
            m.x = q[0] + nx * rr; m.y = q[1] + ny * rr;
            m.path.push([m.x, m.y]);
          }
        }
        if (m.x < m.r + 4) { m.x = m.r + 4; m.vx = Math.abs(m.vx); m.path.push([m.x, m.y]); }
        if (m.x > LEFT - m.r - 4) { m.x = LEFT - m.r - 4; m.vx = -Math.abs(m.vx); m.path.push([m.x, m.y]); }
        if (!m.zone && m.y > LEDGE_TOP + 20) {
          const inGroup = m.x < GAP[0] || m.x > GAP[1];
          if (inGroup) {
            const sl = SLOT_X.find(z => m.x >= z[0] && m.x < z[1]); const slot = sl ? sl[2] : (m.x < GAP[0] ? 2 : 3);
            this.hit[slot]++; this.award(m.team, slot, m.v); continue;
          }
          m.zone = 1; m.path = [];
        }
        if (m.zone && m.y > ITEMY + 30) {
          let it = 0; for (let k = 0; k < 5; k++) if (m.x >= ITEM_X[k]) it = k;
          this.giveItem(m.team, it);
          if (this.marbles.filter(q => q.lift).length < 4) { m.lift = 1; m.lx = rand(-110, 110); m.vy = -120; m.vx *= .3; m.path = []; live.push(m); }
          continue;
        }
        if (m.path.length > 2) m.path.shift();
        live.push(m);
      }
      this.marbles = live.slice(-80);
    }
    sampleFrontierSparks() {
      if (this.frame % 3 !== 0) return;
      let added = 0, tries = 0;
      while (added < 40 && tries < 500) {
        tries++;
        const i = (Math.random() * GS * GS) | 0;
        const t = this.grid[i]; if (t > 3) continue;
        const x = i % GS, y = (i / GS) | 0;
        let edge = false;
        if (x > 0 && this.grid[i - 1] !== t) edge = true;
        else if (x < GS - 1 && this.grid[i + 1] !== t) edge = true;
        else if (y > 0 && this.grid[i - GS] !== t) edge = true;
        else if (y < GS - 1 && this.grid[i + GS] !== t) edge = true;
        if (!edge) continue;
        this.frontierSparks.push({
          x: x * S + rand(0, S), y: y * S + rand(0, S), team: t,
          life: .35 + Math.random() * .55, vx: rand(-22, 22), vy: rand(-22, 22)
        });
        added++;
      }
      if (this.frontierSparks.length > 700) this.frontierSparks = this.frontierSparks.slice(-550);
    }
    tick(dt) {
      if (this.paused || this.over) return;
      if (dt > 0) this.fpsEMA = this.fpsEMA * .9 + (1 / dt) * .1;
      this.t = Math.max(0, this.t + dt); this.frame++; this.expandClock += dt;
      for (let t = 0; t < 4; t++) {
        if (t !== this.player || this.autoAim) {
          // centre-focused opening, then a widening sweep across own quadrant (ref: beams meet centre at 0:10)
          const [bx, by] = BASES[t], c = Math.atan2(G / 2 - by, G / 2 - bx);
          if (this.t < 12) { this.aim[t] = c; this.lock[t] = null; }
          else {
            // threat lock: normal bullets within 2x shield radius, big balls within half the map
            let best = null, bd = 1e9;
            if ((this.frame + t) % 3 === 0) {
              for (const q of this.shots) {
                if (q.team === t) continue;
                const d = Math.hypot(q.x - bx, q.y - by), lim = q.kind === 2 ? G * .5 : 200;
                if (d < lim && d < bd) { bd = d; best = q; }
              }
              this.lock[t] = best;
            }
            const L = this.lock[t];
            if (L && L.x > -20) {
              const want = Math.atan2(L.y - by, L.x - bx);
              let da = ((want - this.aim[t] + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
              this.aim[t] += clamp(da, -3.2 * dt, 3.2 * dt);
            } else {
              // free continuous rotation (spin), speed/direction per team
              this.aim[t] += this.spin[t] * dt;
            }
            this.aim[t] = ((this.aim[t] + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI;
          }
        }
        if (t === this.player && this.autoAim) this.playerAim = this.aim[t];
        this.cool[t] -= dt; if (this.t < 2.5) continue;
        const rate = clamp(.11 - this.t * .0001, .04, .11) / this.power[t];
        if (t === this.player) {
          if (!this.autoAim) this.aim[t] = this.playerAim;
          if (this.firing && this.cool[t] <= 0) { this.spawn(t, 0, this.t < 20 ? 10 : 14); this.cool[t] = .04; }
          else if (this.autoFire && this.cool[t] <= 0) { this.spawn(t, 0, this.t < 12 ? 9 : this.t < 50 ? 12 : 16); this.cool[t] = rate; }
        } else if (this.cool[t] <= 0) {
          this.spawn(t, 0, this.t < 12 ? 9 : this.t < 50 ? 12 : 16);
          this.cool[t] = rate * (.7 + Math.random() * .35);
          if (Math.random() < (this.t < 40 ? .002 : this.t < 120 ? .02 : .06) * this.power[t] && this.aiItems[t].some(v => v > 0)) {
            const i = this.aiItems[t].findIndex(v => v > 0); this.use(t, i);
          }
        }
      }
      if (this.t > 2.5 && this.t < 14) { this.growClock = (this.growClock || 0) + dt; if (this.growClock > .4) { this.growClock = 0; this.growBases(5 + Math.min(1, this.t / 10) * 10); } }
      this.tickMarbles(dt);
      this.powerClock += dt;
      if (this.powerClock > 6) {
        this.powerClock = 0;
        { const lo = this.t < 90 ? .75 : .35, hi = this.t < 90 ? 1.3 : 1.9; for (let t = 0; t < 4; t++) this.power[t] = clamp(this.power[t] * rand(.8, 1.25), lo, hi); }
        // leader snowball after 90s: the top team gets a boost (ref: one team floods)
        if (this.t > 90) { const lead = this.share.indexOf(Math.max(...this.share)); this.power[lead] = Math.min(1.6, this.power[lead] * 1.05); const last = this.share.indexOf(Math.min(...this.share)); this.power[last] = Math.min(1.9, this.power[last] * 1.2); if (Math.random() < .5) { const bag = lead === this.player ? this.items : this.aiItems[lead]; bag[Math.random() < .5 ? 0 : 3]++; } }
      }
      this.heatClock += dt;
      if (this.heatClock > .25) {
        const k = Math.pow(this.t < 20 ? .96 : .8, this.heatClock * 4); this.heatClock = 0;
        const h = this.heat, gr = this.grid, f = this.flood ?? -1, kf = Math.pow(.985, 4 * .25 / .25); for (let i = 0; i < h.length; i++) h[i] *= gr[i] === f ? .985 : k;
        this.dirty = true;
      }
      if (this.t > 150) {
        const lead = this.share.indexOf(Math.max(...this.share));
        this.flood = lead;
        if (!this.waves.some(w => w.team === lead) && this.t - (this.lastStorm[lead] || -99) > 9) {
          this.lastStorm[lead] = this.t;
          const [bx, by] = BASES[lead];
          this.waves.push({ team: lead, r: 90, a: Math.atan2(G / 2 - by, G / 2 - bx) + rand(-.25, .25), half: .9, sp: 170, life: 0, big: true });
        }
        if (this.t > 235 && this.t < 380 && !this.shots.some(q => q.kind === 2)) { const lead = (Math.random() * 4) | 0, bag = lead === this.player ? this.items : this.aiItems[lead]; bag[3]++; this.use(lead, 3); }
        if (Math.random() < dt * (this.t > 240 ? .3 : this.t > 120 ? .1 : .015) && this.shots.filter(q => q.kind === 2).length < 3) { const lead = [0, 1, 2, 3][(Math.random() * 4) | 0]; const bag = lead === this.player ? this.items : this.aiItems[lead]; bag[3]++; this.use(lead, 3); }
      } else this.flood = -1;
      // storm sweep waves: expanding arc that floods cells (ignores shields beyond base radius)
      for (const w of this.waves) {
        w.r += w.sp * dt; w.life += dt;
        const [bx, by] = BASES[w.team], step = (S * .8) / w.r;
        for (let a = w.a - w.half; a <= w.a + w.half; a += step) {
          for (let dr = 0; dr < 3; dr++) {
            const x = bx + Math.cos(a) * (w.r - dr * S), y = by + Math.sin(a) * (w.r - dr * S);
            const gx = (x / S) | 0, gy = (y / S) | 0; if (gx < 0 || gy < 0 || gx >= GS || gy >= GS) continue;
            const i = gy * GS + gx; if (this.grid[i] !== w.team) { this.grid[i] = w.team; this.dirty = true; } this.heat[i] = 1;
          }
        }
      }
      this.waves = this.waves.filter(w => w.r < (w.big ? 820 : 600) && w.life < 8);
      this.caClock = (this.caClock || 0) + dt;
      if (this.caClock > .5) { this.caClock = 0; this.smoothFront(); }

      const active = [], trailMax = this.t > 80 ? 22 : this.t > 25 ? 16 : 12;
      for (const p of this.shots) {
        p.trail.push([p.x, p.y]); if (p.trail.length > (p.kind === 2 ? 140 : trailMax)) p.trail.shift();
        p.x += p.vx * 60 * dt; p.y += p.vy * 60 * dt;
        if (p.x < -20 || p.y < -20 || p.x > G + 20 || p.y > G + 20) continue;
        if (!this.hitShot(p)) active.push(p);
      }
      this.shots = active;
      this.sparks = this.sparks.filter(s => { s.life -= dt * (s.burst ? .7 : 1.8); return s.life > 0; }).slice(-900);
      for (const s of this.frontierSparks) { s.life -= dt * 1.4; s.x += s.vx * dt; s.y += s.vy * dt; }
      this.frontierSparks = this.frontierSparks.filter(s => s.life > 0);
      this.sampleFrontierSparks();

      // decorative ribbons (mid-weight trails)
      if (this.frame % 2 === 0 && this.t > 2.5) {
        for (let t = 0; t < 4; t++) {
          const [bx, by] = BASES[t], a = this.aim[t], n = this.t < 15 ? 6 : this.t < 50 ? 9 : 12;
          for (let k = 0; k < n; k++) {
            const ang = a + rand(-.32, .32), sp = rand(8, 18);
            this.ribbons.push({ team: t, x: bx + rand(-6, 6), y: by + rand(-6, 6), vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, life: .7 + Math.random() * .8, trail: [] });
          }
        }
        if (this.ribbons.length > RIBBON_CAP) this.ribbons = this.ribbons.slice(-RIBBON_CAP + 200);
      }
      const rb = [];
      for (const p of this.ribbons) {
        p.trail.push([p.x, p.y]); if (p.trail.length > 16) p.trail.shift();
        p.x += p.vx * 60 * dt; p.y += p.vy * 60 * dt; p.life -= dt;
        if (p.life <= 0 || p.x < 0 || p.y < 0 || p.x > G || p.y > G) continue;
        const gx = (p.x / S) | 0, gy = (p.y / S) | 0;
        if (gx >= 0 && gy >= 0 && gx < GS && gy < GS) {
          const own = this.grid[this.id(gx, gy)];
          if (own !== p.team) p.life -= dt * 1.1;
        }
        rb.push(p);
      }
      this.ribbons = rb;

      // dense silk-thread particles (GPU ParticleContainer target)
      {
        const spawnN = this.t < 2.5 ? 0 : this.t < 15 ? 100 : this.t < 40 ? 130 : this.t < 90 ? 150 : 170;
        for (let t = 0; t < 4; t++) {
          const [bx, by] = BASES[t], a = this.aim[t];
          const toCenter = Math.atan2(G / 2 - by, G / 2 - bx);
          for (let k = 0; k < spawnN; k++) {
            // mostly center-seeking tight cone (Douyin silk beams), some aim weave
            // ~35% tight beam along aim (team-coloured core), rest a wide fine-hair fan
            const beam = (k % 3 === 0);
            const base = a; // streams follow the turret barrel
            const spread = beam ? 0.035 : 0.6;
            const ang = base + rand(-spread, spread), sp = rand(7, 18);
            const jx = rand(-4, 4), jy = rand(-4, 4);
            this.pushSilk(beam ? t + 4 : t, bx + jx, by + jy, Math.cos(ang) * sp, Math.sin(ang) * sp, .9 + Math.random() * 1.3);
          }
        }
        const silk = this.silk;
        let w = 0;
        for (let i = 0; i < this.silkCount; i++) {
          const o = i * 7;
          let x = silk[o], y = silk[o + 1], vx = silk[o + 2], vy = silk[o + 3], life = silk[o + 4], tm = silk[o + 5];
          // micro weave for silk-fiber look
          const px = -vy * 0.04, py = vx * 0.04;
          x += (vx + px * Math.sin(life * 14 + i)) * 60 * dt;
          y += (vy + py * Math.cos(life * 14 + i)) * 60 * dt;
          life -= dt;
          if (life <= 0 || x < -12 || y < -12 || x > G + 12 || y > G + 12) continue;
          if ((i & 31) === 0) {
            const gx = (x / S) | 0, gy = (y / S) | 0;
            if (gx >= 0 && gy >= 0 && gx < GS && gy < GS) {
              const own = this.grid[this.id(gx, gy)];
              if (own !== (tm & 3) && own < 4) {
                life -= dt * 0.25;
              }
            }
          }
          const d = w * 7;
          silk[d] = x; silk[d + 1] = y; silk[d + 2] = vx; silk[d + 3] = vy;
          silk[d + 4] = life; silk[d + 5] = tm; silk[d + 6] = Math.atan2(vy, vx);
          w++;
        }
        this.silkCount = w;
      }

      const count = [0, 0, 0, 0];
      for (let i = 0; i < this.grid.length; i++) { const v = this.grid[i]; if (v < 4) count[v]++; }
      this.share = count.map(v => v / (GS * GS));
      for (let t = 0; t < 4; t++) {
        this.score[t] = Math.max(0, this.score[t] + dt * (12000 + this.share[t] * 60000));
        this.level[t] = Math.min(99, Math.floor(this.t / 30));
        this.ammo[t] += dt * (3000 + this.t * 60) * this.power[t] * (this.ammo[t] < 3e6 ? 12 : 1);
      }
      if (this.t >= MATCH) { this.winner = this.share.indexOf(Math.max(...this.share)); this.over = true; }
      else if (this.share.some(v => v > .97 && this.t > 700)) { this.winner = this.share.indexOf(Math.max(...this.share)); this.over = true; }
    }
  }

  /* ===================== LEFT BOARD (Canvas2D → texture) ===================== */
  function drawIcon(c, i, x, y) {
    c.save(); c.translate(x, y); c.scale(.78, .78); c.strokeStyle = '#bfcbd4'; c.fillStyle = '#bfcbd4'; c.lineWidth = 1.7; c.lineCap = 'round';
    if (i === 0) { // 风暴: tornado
      for (let k = 0; k < 4; k++) { c.beginPath(); c.moveTo(-10 + k * 2.5, -7 + k * 4.5); c.lineTo(10 - k * 1.5, -7 + k * 4.5); c.stroke(); }
    } else if (i === 1) { // 机枪: rifle
      c.beginPath(); c.moveTo(-13, -1); c.lineTo(12, -1); c.lineTo(12, 1.5); c.lineTo(-2, 1.5); c.lineTo(-5, 6); c.lineTo(-8, 6); c.lineTo(-7, 1.5); c.lineTo(-13, 2); c.closePath(); c.fill();
      c.fillRect(2, 1.5, 2.5, 4); c.fillRect(12, -2.2, 3, 1.2);
    } else if (i === 2) { // 护盾
      c.beginPath(); c.moveTo(0, -8); c.lineTo(7, -5); c.lineTo(6, 3); c.lineTo(0, 8); c.lineTo(-6, 3); c.lineTo(-7, -5); c.closePath(); c.stroke();
      c.beginPath(); c.moveTo(0, -4); c.lineTo(3.5, -2.5); c.lineTo(3, 2); c.lineTo(0, 4.5); c.lineTo(-3, 2); c.lineTo(-3.5, -2.5); c.closePath(); c.fill();
    } else if (i === 3) { // 大球: comet ball
      c.beginPath(); c.arc(5, 0, 5, 0, 7); c.fill();
      c.globalAlpha = .7; for (let k = 0; k < 3; k++) { c.beginPath(); c.moveTo(1, -3 + k * 3); c.lineTo(-11 + k, -4 + k * 3.5); c.stroke(); }
    } else { // 狙击: scope
      c.beginPath(); c.arc(0, 0, 6.5, 0, 7); c.stroke();
      c.beginPath(); c.moveTo(-11, 0); c.lineTo(11, 0); c.moveTo(0, -9); c.lineTo(0, 9); c.stroke();
      c.beginPath(); c.arc(0, 0, 1.6, 0, 7); c.fill();
    }
    c.restore();
  }
  function pillar(c, x, w, top, bot) {
    const g = c.createLinearGradient(x, 0, x + w, 0);
    g.addColorStop(0, '#1b3346'); g.addColorStop(.5, '#24425a'); g.addColorStop(1, '#122435');
    c.beginPath(); c.moveTo(x, bot); c.lineTo(x, top + 4); c.quadraticCurveTo(x, top, x + 4, top); c.lineTo(x + w - 3, top + 2); c.quadraticCurveTo(x + w, top + 3, x + w, top + 6); c.lineTo(x + w, bot); c.closePath();
    c.fillStyle = g; c.fill(); c.strokeStyle = 'rgba(150,185,205,.75)'; c.lineWidth = 1.3; c.stroke();
  }
  const LPILLARS = [[0, 12, 428], [42, 24, 433], [116, 26, 443], [209, 13, 456]];
  const SLOT_LABEL_X = [27, 93, 176, 582, 668, 732];
  const IPILLARS = [[0, 12, 918], [137, 23, 928], [290, 23, 934], [448, 23, 934], [601, 23, 928], [748, 12, 918]];
  function drawLeftTo(c, game) {
    if (!drawLeftTo.cache) {
      const cv = document.createElement('canvas'); cv.width = LEFT; cv.height = H;
      const b = cv.getContext('2d');
      const bg = b.createRadialGradient(LEFT * .5, H * .45, 50, LEFT * .5, H * .45, 760);
      bg.addColorStop(0, '#0c1826'); bg.addColorStop(1, '#060e18');
      b.fillStyle = bg; b.fillRect(0, 0, LEFT, H);
      b.strokeStyle = 'rgba(120,160,190,.07)'; b.lineWidth = 1;
      for (let x = 200; x < LEFT; x += 200) { b.beginPath(); b.moveTo(x + .5, 0); b.lineTo(x + .5, H); b.stroke(); }
      for (let y = 200; y < H; y += 200) { b.beginPath(); b.moveTo(0, y + .5); b.lineTo(LEFT, y + .5); b.stroke(); }
      b.save(); b.setLineDash([6, 6]); b.strokeStyle = 'rgba(150,170,190,.35)'; b.beginPath(); b.moveTo(0, 50.5); b.lineTo(LEFT, 50.5); b.stroke(); b.restore();
      // centre lift band + arrows
      const gl = b.createLinearGradient(0, 455, 0, 520); gl.addColorStop(0, 'rgba(40,150,170,0)'); gl.addColorStop(.5, 'rgba(50,170,190,.22)'); gl.addColorStop(1, 'rgba(40,150,170,0)');
      b.fillStyle = gl; b.fillRect(GAP[0], 455, GAP[1] - GAP[0], 65);
      const cg = b.createRadialGradient(380, 487, 5, 380, 487, 120); cg.addColorStop(0, 'rgba(90,210,230,.25)'); cg.addColorStop(1, 'rgba(0,0,0,0)'); b.fillStyle = cg; b.fillRect(260, 440, 240, 95);
      b.strokeStyle = 'rgba(110,200,215,.55)'; b.lineWidth = 1.4;
      for (const ax of [253, 316, 380, 443, 506]) for (const [y0, y1] of [[485, 463], [512, 490]]) {
        b.beginPath(); b.moveTo(ax, y0); b.lineTo(ax, y1); b.moveTo(ax - 3.5, y1 + 5); b.lineTo(ax, y1); b.lineTo(ax + 3.5, y1 + 5); b.stroke();
      }
      // ledge groups
      for (const [g0, g1] of LGROUP) { b.fillStyle = 'rgba(14,30,46,.55)'; b.fillRect(g0, 455, g1 - g0, 85); b.strokeStyle = 'rgba(150,185,205,.7)'; b.lineWidth = 1.3; b.beginPath(); b.moveTo(g0, 540.5); b.lineTo(g1, 540.5); b.stroke(); }
      // item area
      const ig = b.createLinearGradient(0, 925, 0, 1052); ig.addColorStop(0, 'rgba(20,40,58,.15)'); ig.addColorStop(1, 'rgba(24,48,68,.55)');
      b.fillStyle = ig; b.fillRect(0, 925, LEFT, 127);
      b.strokeStyle = 'rgba(150,185,205,.7)'; b.beginPath(); b.moveTo(0, 1052.5); b.lineTo(LEFT, 1052.5); b.stroke();
      b.strokeStyle = 'rgba(120,160,185,.55)'; b.lineWidth = 1; b.strokeRect(.5, .5, LEFT - 1, H - 1);
      drawLeftTo.cache = cv;
    }
    c.drawImage(drawLeftTo.cache, 0, 0);
    // pegs (drift slowly)
    for (const P of [game.pegs, game.lowerPegs]) for (const q of P) {
      c.fillStyle = 'rgba(140,150,162,.8)'; c.beginPath(); c.arc(q[0], q[1], 4.6, 0, 7); c.fill();
      c.fillStyle = 'rgba(200,208,216,.45)'; c.beginPath(); c.arc(q[0] - 1.2, q[1] - 1.2, 2, 0, 7); c.fill();
    }
    // slot hit tint
    for (const [x0, x1, sl] of SLOT_X) { const f = game.slotFlash[sl]; if (f && f.life > 0) { c.fillStyle = rgb(TEAMS[f.team].c, .45 * f.life); c.fillRect(x0 + 2, 448, x1 - x0 - 4, 92); } }
    for (let k = 0; k < 5; k++) { const f = game.itemFlash[k]; if (f && f.life > 0) { c.fillStyle = rgb(TEAMS[f.team].c, .3 * f.life); c.fillRect(ITEM_X[k] + 12, 935, ITEM_X[k + 1] - ITEM_X[k] - 24, 117); } }
    // wide translucent trajectory bands for big marbles (ref: long straight light strips)
    c.save(); c.lineCap = 'butt';
    const big = game.marbles.filter(m => m.v >= 1.6e4 && !m.lift && !m.wait && m.path.length).sort((a, b) => b.v - a.v).slice(0, 3);
    for (const m of big) {
      const o = m.path[m.path.length - 1], dx = m.x - o[0], dy = m.y - o[1], L = Math.hypot(dx, dy);
      if (L < 70) continue;
      { const sp = Math.hypot(m.vx, m.vy) || 1; if ((dx * m.vx + dy * m.vy) / (L * sp) < .8) continue; }
      const k = Math.min(1, 520 / L), sx = m.x - dx * k, sy = m.y - dy * k;
      const gg = c.createLinearGradient(sx, sy, m.x, m.y); gg.addColorStop(0, rgb(TEAMS[m.team].c, 0)); gg.addColorStop(1, rgb(TEAMS[m.team].c, .2));
      c.strokeStyle = gg; c.lineWidth = m.r * 1.7; c.beginPath(); c.moveTo(sx, sy); c.lineTo(m.x, m.y); c.stroke();
    }
    c.restore();
    // marbles: comet tail + glossy sphere + label
    for (const m of game.marbles) {
      const team = TEAMS[m.team], r = m.r, sp = Math.hypot(m.vx, m.vy) || 1, ux = m.vx / sp, uy = m.vy / sp;
      const L = Math.min(30, 8 + r * 1.5) * (m.wait > 0 ? 0 : 1);
      c.fillStyle = rgb(team.hi, .16); c.beginPath(); c.arc(m.x, m.y, r * 1.45, 0, 7); c.fill();
      const tg = c.createLinearGradient(m.x, m.y, m.x - ux * L, m.y - uy * L);
      tg.addColorStop(0, rgb(team.hi, .75)); tg.addColorStop(1, rgb(team.c, 0));
      c.fillStyle = tg; c.beginPath(); c.moveTo(m.x + uy * r * .7, m.y - ux * r * .7); c.lineTo(m.x - ux * L, m.y - uy * L); c.lineTo(m.x - uy * r * .7, m.y + ux * r * .7); c.closePath(); c.fill();
      const g = c.createRadialGradient(m.x - r * .35, m.y - r * .45, r * .1, m.x, m.y, r);
      g.addColorStop(0, rgb([Math.min(255, team.hi[0] + 70), Math.min(255, team.hi[1] + 70), Math.min(255, team.hi[2] + 70)])); g.addColorStop(.45, rgb(team.c)); g.addColorStop(1, rgb([team.c[0] * .55, team.c[1] * .55, team.c[2] * .55]));
      c.fillStyle = g; c.beginPath(); c.arc(m.x, m.y, r, 0, 7); c.fill();
      c.strokeStyle = 'rgba(255,255,255,.55)'; c.lineWidth = 1; c.stroke();
      c.fillStyle = 'rgba(255,255,255,.55)'; c.beginPath(); c.ellipse(m.x - r * .3, m.y - r * .55, r * .4, r * .18, -.4, 0, 7); c.fill();
      const txt = fmt(m.v);
      c.fillStyle = '#fff'; c.textAlign = 'center'; c.textBaseline = 'middle';
      c.font = `800 ${Math.max(7, Math.round(r * (txt.length > 3 ? .6 : .72)))}px Arial,sans-serif`;
      c.lineWidth = 2.4; c.strokeStyle = rgb([team.c[0] * .35, team.c[1] * .35, team.c[2] * .35], .9); c.strokeText(txt, m.x, m.y + .5); c.fillText(txt, m.x, m.y + .5);
    }
    c.textBaseline = 'alphabetic';
    // pillars + labels drawn above marbles (marbles drop into cups)
    for (const [x, w, top] of LPILLARS) { pillar(c, x, w, top, 540); pillar(c, LEFT - x - w, w, top, 540); }
    for (let i = 0; i < 6; i++) {
      c.fillStyle = '#f2f8fc'; c.textAlign = 'center'; c.font = '800 23px Arial,sans-serif';
      c.fillText('X' + MULT[i], SLOT_LABEL_X[i], 510);
      c.font = '700 14px Arial,sans-serif'; c.fillStyle = '#dfeaf2'; c.fillText('' + game.hit[i], SLOT_LABEL_X[i], 528);
    }
    for (const [x, w, top] of IPILLARS) pillar(c, x, w, top, 1052);
    for (let i = 0; i < 5; i++) {
      const cx = (ITEM_X[i] + ITEM_X[i + 1]) / 2 + (i === 0 ? 4 : i === 4 ? -4 : 0), dy = [0, 8, 12, 8, 0][i];
      drawIcon(c, i, cx, 981 + dy);
      c.fillStyle = '#d7e6f0'; c.textAlign = 'center'; c.font = '600 15px "PingFang SC","Microsoft YaHei",sans-serif';
      c.fillText(NAMES[i], cx, 1009 + dy);
      c.strokeStyle = 'rgba(150,190,210,.25)'; c.lineWidth = 1; c.beginPath(); c.moveTo(cx - 30, 1040); c.lineTo(cx + 30, 1040); c.stroke();
      c.fillStyle = '#f2f8fc'; c.font = '700 14px Arial,sans-serif'; c.fillText('' + game.items[i], cx, 1071);
    }
  }

  /* ===================== PIXI RENDERER ===================== */
  class PixiView {
    constructor(app) {
      this.app = app;
      this.root = new PIXI.Container();
      app.stage.addChild(this.root);

      // left board offscreen
      this.leftCv = document.createElement('canvas');
      this.leftCv.width = LEFT; this.leftCv.height = H;
      this.leftCtx = this.leftCv.getContext('2d', { alpha: false });
      this.leftTex = PIXI.Texture.from(this.leftCv);
      this.leftSpr = new PIXI.Sprite(this.leftTex);
      this.root.addChild(this.leftSpr);

      // arena layer
      this.arena = new PIXI.Container();
      this.arena.x = AX; this.arena.y = AY;
      this.root.addChild(this.arena);
      this.arenaMask = new PIXI.Graphics().rect(AX, AY, G, G).fill(0xffffff); this.root.addChild(this.arenaMask); this.arena.mask = this.arenaMask;

      // bg
      this.bg = new PIXI.Graphics().rect(0, 0, G, G).fill(0x02080f);
      this.arena.addChild(this.bg);

      // stars
      this.starG = new PIXI.Graphics();
      this.arena.addChild(this.starG);

      // territory textures
      this.terrCv = document.createElement('canvas');
      this.terrCv.width = this.terrCv.height = TRES;
      this.terrCtx = this.terrCv.getContext('2d', { willReadFrequently: true });
      this.terrImg = this.terrCtx.createImageData(TRES, TRES);

      this.edgeCv = document.createElement('canvas');
      this.edgeCv.width = this.edgeCv.height = TRES;
      this.edgeCtx = this.edgeCv.getContext('2d');
      this.edgeImg = this.edgeCtx.createImageData(TRES, TRES);

      this.terrTex = PIXI.Texture.from(this.terrCv);
      this.edgeTex = PIXI.Texture.from(this.edgeCv);

      // Low-res blur targets (cheap on software GL, still look foamy when upscaled)
      const BLUR_RES = 384;
      this._blurRes = BLUR_RES;
      this.softRT = PIXI.RenderTexture.create({ width: BLUR_RES, height: BLUR_RES });
      this.foamRT = PIXI.RenderTexture.create({ width: BLUR_RES, height: BLUR_RES });

      this._terrBlit = new PIXI.Sprite(this.terrTex);
      this._terrBlit.width = BLUR_RES; this._terrBlit.height = BLUR_RES;
      this._terrBlit.filters = [new PIXI.BlurFilter({ strength: 5, quality: 3 })];

      this._edgeBlit = new PIXI.Sprite(this.edgeTex);
      this._edgeBlit.width = BLUR_RES; this._edgeBlit.height = BLUR_RES;
      this._edgeBlit.filters = [new PIXI.BlurFilter({ strength: 6, quality: 2 })];

      // soft nebula fill (upscaled blurred RT)
      this.softSpr = new PIXI.Sprite(this.softRT);
      this.softSpr.width = G; this.softSpr.height = G;
      this.softSpr.alpha = 0.0; this.softSpr.visible = false;
      this.arena.addChild(this.softSpr);

      // crisp color core — lower alpha so edges stay soft/organic
      this.crispSpr = new PIXI.Sprite(this.terrTex);
      this.crispSpr.width = G; this.crispSpr.height = G;
      this.crispSpr.alpha = 1; this.terrTex.source.scaleMode = 'nearest';
      this.arena.addChild(this.crispSpr);

      // frontier foam bloom (upscaled)
      this.foamSpr = new PIXI.Sprite(this.foamRT);
      this.foamSpr.width = G + 10; this.foamSpr.height = G + 10;
      this.foamSpr.x = -5; this.foamSpr.y = -5;
      this.foamSpr.blendMode = 'add';
      this.foamSpr.alpha = 0.9;
      this.arena.addChild(this.foamSpr);

      // no raw edge overlay — hard pixels caused blocky frontiers; foam comes only from blurred RT

      this._foamDirty = true;

      // grid overlay
      this.gridG = new PIXI.Graphics();
      for (let i = 0; i <= 20; i++) {
        const q = i * 50;
        this.gridG.moveTo(q, 0).lineTo(q, G);
        this.gridG.moveTo(0, q).lineTo(G, q);
      }
      this.gridG.stroke({ width: 1, color: 0x8cafd2, alpha: 0.07 });

      this.arena.addChild(this.gridG);
      // glow / silk textures
      this.dotTex = PIXI.Texture.from(bakeGlow(32, [[0, 'rgba(255,255,255,1)'], [.3, 'rgba(255,255,255,.7)'], [.7, 'rgba(200,230,255,.2)'], [1, 'rgba(0,0,0,0)']]));
      this.silkTex = PIXI.Texture.from(bakeSilk(64, 10));
      this.sparkTex = PIXI.Texture.from(SPR2D.spark);
      this.teamGlowTex = TEAMS.map(t => PIXI.Texture.from(SPR2D.team[TEAMS.indexOf(t)]));

      // silk particle container (thousands of additive threads)
      this.silkPC = new PIXI.ParticleContainer({
        dynamicProperties: { position: true, scale: true, rotation: true, color: true }
      });
      this.silkPC.blendMode = 'add';
      this.silkParticles = [];
      for (let i = 0; i < SILK_CAP; i++) {
        const p = new PIXI.Particle({ texture: this.silkTex });
        p.anchorX = 0.5; p.anchorY = 0.5;
        p.alpha = 0; p.scaleX = 0; p.scaleY = 0;
        this.silkPC.addParticle(p);
        this.silkParticles.push(p);
      }
      this.arena.addChild(this.silkPC);

      // shot ribbons via Graphics (beams / big balls drawn each frame)
      this.shotG = new PIXI.Graphics();
      this.shotG.blendMode = 'add';
      this.arena.addChild(this.shotG);

      this.bigBallLayer = new PIXI.Container();
      this.arena.addChild(this.bigBallLayer);

      this.sparkPC = new PIXI.ParticleContainer({
        dynamicProperties: { position: true, scale: true, color: true }
      });
      this.sparkPC.blendMode = 'add';
      this.sparkParticles = [];
      for (let i = 0; i < 800; i++) {
        const p = new PIXI.Particle({ texture: this.sparkTex });
        p.anchorX = 0.5; p.anchorY = 0.5; p.alpha = 0; p.scaleX = 0; p.scaleY = 0;
        this.sparkPC.addParticle(p);
        this.sparkParticles.push(p);
      }
      this.arena.addChild(this.sparkPC);

      // bases + meters drawn with Graphics + Text (readable on top)
      this.hud = new PIXI.Container();
      this.root.addChild(this.hud);
      this.baseG = new PIXI.Graphics();
      this.hud.addChild(this.baseG);
      this.baseTexts = [];
      for (let t = 0; t < 4; t++) {
        const ammo = new PIXI.Text({ text: '0M', style: { fontFamily: 'Arial', fontSize: 32, fontWeight: '800', fill: 0xffffff } });
        const sec = new PIXI.Text({ text: '0', style: { fontFamily: 'Arial', fontSize: 16, fontWeight: '700', fill: 0xdcecff } });
        ammo.anchor.set(0, 0.5); sec.anchor.set(0.5, 0.5);
        this.hud.addChild(ammo); this.hud.addChild(sec);
        const lab = new PIXI.Text({ text: '最强火力\n+1M', style: { fontFamily: '"PingFang SC","Microsoft YaHei",Arial,sans-serif', fontSize: 11, fontWeight: '700', fill: 0xe8f0f6, align: 'center', lineHeight: 14 } });
        const zero = new PIXI.Text({ text: '0.00', style: { fontFamily: 'Arial', fontSize: 14, fontWeight: '800', fill: 0xffffff } });
        lab.anchor.set(.5, 1); zero.anchor.set(0, .5); this.hud.addChild(lab); this.hud.addChild(zero);
        this.baseTexts.push({ ammo, sec, lab, zero });
      }
      this.meterG = new PIXI.Graphics();
      this.hud.addChild(this.meterG);
      this.meterTexts = [];
      for (let i = 0; i < 4; i++) {
        const pct = new PIXI.Text({ text: '0.00%', style: { fontFamily: 'Arial', fontSize: 17, fontWeight: '800', fill: 0xffffff } });
        const lv = new PIXI.Text({ text: '0', style: { fontFamily: 'Arial', fontSize: 14, fontWeight: '800', fill: 0xffffff } });
        pct.anchor.set(0.5, 0.5); lv.anchor.set(0.5, 0.5);
        this.hud.addChild(pct); this.hud.addChild(lv);
        const mk = (sz, col, txt) => { const o = new PIXI.Text({ text: txt, style: { fontFamily: 'Arial, "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: sz, fontWeight: '700', fill: col } }); o.anchor.set(.5, .5); this.hud.addChild(o); return o; };
        const n = mk(11, 0x8796a4, '0'), of = mk(10, 0x8796a4, '/ 800'), ex = mk(10, 0xc9d6e0, '额外弹珠'), full = mk(9, 0xc9d6e0, '100%');
        const ticks = ['75%', '50%', '25%'].map(q => mk(9, 0xa9b8c4, q));
        this.meterTexts.push({ pct, lv, n, of, ex, full, ticks });
      }

      this.border = new PIXI.Graphics().rect(AX, AY, G, G).stroke({ width: 1.4, color: 0x5a8cb4, alpha: 0.55 });
      this.root.addChild(this.border);

      this.pauseG = new PIXI.Graphics();
      this.pauseTxt = new PIXI.Text({ text: '暂停', style: { fontFamily: 'sans-serif', fontSize: 48, fontWeight: '700', fill: 0xffffff } });
      this.pauseTxt.anchor.set(0.5); this.pauseTxt.x = W / 2; this.pauseTxt.y = H / 2;
      this.pauseG.visible = false; this.pauseTxt.visible = false;
      this.root.addChild(this.pauseG); this.root.addChild(this.pauseTxt);

      this._starsDrawn = false;
    }

    drawStars(game) {
      if (this._starsDrawn) return;
      this.starG.clear();
      for (const [x, y, a, s] of game.stars) {
        this.starG.circle(x, y, s).fill({ color: 0xbedcff, alpha: a * 0.55 });
      }
      this._starsDrawn = true;
    }

    /** Nebula-foam territory: domain-warped 2x sampling + value-noise texture + dark seam + patchy foam rim */
    buildNoise() {
      const N = TRES, vn = (x, y, f, seed) => {
        // cheap value noise
        const xi = Math.floor(x * f), yi = Math.floor(y * f), xf = x * f - xi, yf = y * f - yi;
        const h = (a, b) => { const n = Math.sin(a * 127.1 + b * 311.7 + seed * 74.7) * 43758.5453; return n - Math.floor(n); };
        const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
        return (h(xi, yi) * (1 - u) + h(xi + 1, yi) * u) * (1 - v) + (h(xi, yi + 1) * (1 - u) + h(xi + 1, yi + 1) * u) * v;
      };
      this.wx = new Float32Array(N * N); this.wy = new Float32Array(N * N); this.tex = new Float32Array(N * N); this.foamN = new Float32Array(N * N);
      for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
        const i = y * N + x;
        const w1 = vn(x, y, .05, 1) + .5 * vn(x, y, .13, 2) + .25 * vn(x, y, .31, 3);
        const w2 = vn(x, y, .05, 4) + .5 * vn(x, y, .13, 5) + .25 * vn(x, y, .31, 6);
        this.wx[i] = (w1 / 1.75 - .5) * 7; this.wy[i] = (w2 / 1.75 - .5) * 7; // grid-cell units
        this.tex[i] = vn(x, y, .04, 7) * .6 + vn(x, y, .11, 8) * .4;
        this.foamN[i] = vn(x, y, .22, 9) * .6 + vn(x, y, .55, 10) * .4;
      }
      this.tNow = 0;
    }
    rebuildTerrain(game) {
      if (!this.wx) this.buildNoise();
      const N = TRES, k = GS / N, d = this.terrImg.data, e = this.edgeImg.data, grid = game.grid, heat = game.heat;
      // chamfer distance (in cells) to nearest boundary, capped — drives rim band thickness
      const dist = this.dist || (this.dist = new Uint8Array(GS * GS));
      for (let y = 0; y < GS; y++) for (let x = 0; x < GS; x++) {
        const i = y * GS + x, t = grid[i];
        dist[i] = (t < 4 && ((x > 0 && grid[i - 1] !== t) || (x < GS - 1 && grid[i + 1] !== t) || (y > 0 && grid[i - GS] !== t) || (y < GS - 1 && grid[i + GS] !== t))) ? 0 : 9;
      }
      for (let y = 1; y < GS; y++) for (let x = 1; x < GS; x++) { const i = y * GS + x; const m = Math.min(dist[i - 1], dist[i - GS]) + 1; if (m < dist[i]) dist[i] = m; }
      for (let y = GS - 2; y >= 0; y--) for (let x = GS - 2; x >= 0; x--) { const i = y * GS + x; const m = Math.min(dist[i + 1], dist[i + GS]) + 1; if (m < dist[i]) dist[i] = m; }
      const seed = (game.frame * 7919) | 0, crisp = clamp((game.t - 200) / 120, 0, 1), wk = .55 * (1 - .85 * crisp);
      for (let y = 0; y < N; y++) {
        for (let x = 0; x < N; x++) {
          const i = y * N + x, o = i << 2;
          let fx = x * k + this.wx[i] * wk, fy = y * k + this.wy[i] * wk;
          const gx = fx < 0 ? 0 : fx >= GS ? GS - 1 : fx | 0, gy = fy < 0 ? 0 : fy >= GS ? GS - 1 : fy | 0;
          const ci = gy * GS + gx, t = grid[ci];
          // grain hash (changes per rebuild → twinkling broken edge)
          let hsh = (i * 374761393 + seed * 668265263) | 0; hsh = (hsh ^ (hsh >>> 13)) * 1274126177; const rnd = ((hsh ^ (hsh >>> 16)) >>> 0) / 4294967296;
          if (t < 4) {
            const team = TEAMS[t], tx = this.tex[i], fn = this.foamN[i], h = heat[ci];
            const thr = 1.1 + fn * 3.4 * (1 - .75 * crisp);               // bubbly rim thickness 0.6–3 cells
            const dd = dist[ci];
            // dark interior: 18–30% tint + fresh-paint glow that fades (ref: recently swept areas bright)
            let br = .16 + (t === game.flood ? .22 : .1) * tx + (t === game.flood ? .55 : .5) * h * h;
            // fine pixel texture: per-cell checker + 50px grid lines baked in
            const px = (gx + gy) & 1 ? 1 : .9; br *= px;
            let r = team.c[0] * br, g = team.c[1] * br, b = team.c[2] * br, ea = 0;
            if (t === game.flood && h > .6) { const wh = (h - .6) * (.6 + tx); r += team.hi[0] * wh * .35; g += team.hi[1] * wh * .3; b += team.hi[2] * wh * .15; }
            if (dd < thr) {
              // thin, strong, broken neon edge — grainy dropout
              const keep = rnd > (.18 + (1 - fn) * .25) * (1 - .8 * crisp);
              if (keep) {
                const core = dd === 0 ? 1 : .75;
                const w = (rnd > .9 && dd === 0) ? 1 : 0;      // white sparkle pixels
                r = (team.hi[0] * core) * (1 - w) + 255 * w; g = (team.hi[1] * core) * (1 - w) + 255 * w; b = (team.hi[2] * core) * (1 - w) + 255 * w;
                ea = 120 + 135 * core;
              } else { r *= 1.8; g *= 1.8; b *= 1.8; }
            }
            d[o] = r > 255 ? 255 : r; d[o + 1] = g > 255 ? 255 : g; d[o + 2] = b > 255 ? 255 : b; d[o + 3] = 255;
            if (ea) { e[o] = team.hi[0]; e[o + 1] = team.hi[1]; e[o + 2] = team.hi[2]; e[o + 3] = ea; } else e[o + 3] = 0;
          } else { d[o + 3] = 0; e[o + 3] = 0; }
        }
      }
      this.terrCtx.putImageData(this.terrImg, 0, 0);
      this.edgeCtx.putImageData(this.edgeImg, 0, 0);
      this.terrTex.source.update();
      this.edgeTex.source.update();
      this._foamDirty = true;
      game.dirty = false;
      game.terrainAge = game.frame;
    }

    updateFoamRT() {
      if (!this._foamDirty) return;
      
      this.app.renderer.render({ container: this._edgeBlit, target: this.foamRT, clear: true });
      this._foamDirty = false;
    }

    syncSilk(game) {
      const parts = this.silkParticles;
      const silk = game.silk;
      const n = game.silkCount;
      const tints = [0xff7a9a, 0x7affcf, 0x7ac4ff, 0xffd27a];
      for (let i = 0; i < SILK_CAP; i++) {
        const p = parts[i];
        if (i >= n) { p.alpha = 0; p.scaleX = 0; p.scaleY = 0; continue; }
        const o = i * 7;
        const life = silk[o + 4], tmr = silk[o + 5] | 0, tm = tmr & 3, isBeam = tmr > 3, ang = silk[o + 6];
        const sp = Math.hypot(silk[o + 2], silk[o + 3]);
        p.x = silk[o]; p.y = silk[o + 1];
        p.rotation = ang;
        // elongated silk thread: length scales with speed
        const len = clamp(0.85 + sp * 0.11, 0.9, 2.8);
        p.scaleX = len;
        p.scaleY = isBeam ? 0.2 : 0.1;
        p.alpha = isBeam ? clamp(life * .8, 0, .45) : clamp(life * 0.45, 0, 0.22);
        p.tint = isBeam ? TEAMS[tm].hex : tints[tm];
      }
    }

    syncSparks(game) {
      const all = game.sparks.concat(game.frontierSparks);
      const parts = this.sparkParticles;
      for (let i = 0; i < parts.length; i++) {
        const p = parts[i];
        if (i >= all.length) { p.alpha = 0; p.scaleX = 0; continue; }
        const s = all[i];
        p.x = s.x; p.y = s.y;
        const sc = s.burst ? (1.5 + (1 - s.life) * 2) : (0.4 + s.life * 0.6);
        p.scaleX = sc; p.scaleY = sc;
        p.alpha = clamp(s.life, 0, 1);
        p.tint = TEAMS[s.team | 0]?.hex || 0xffffff;
      }
    }

    drawShots(game) {
      const g = this.shotG;
      g.clear();
      // clear big balls
      if (!this.ballPool) {
        this.ballPool = [];
        for (let i = 0; i < 10; i++) {
          const c = new PIXI.Container(), glow = new PIXI.Sprite(this.teamGlowTex[0]), ball = new PIXI.Graphics();
          const label = new PIXI.Text({ text: '', style: { fontFamily: 'Arial', fontSize: 26, fontWeight: '900', fill: 0xffffff, stroke: { color: 0x000000, width: 3 } } });
          glow.anchor.set(.5); glow.blendMode = 'add'; label.anchor.set(.5);
          c.addChild(glow, ball, label); c.visible = false; this.bigBallLayer.addChild(c);
          this.ballPool.push({ c, glow, ball, label, key: '' });
        }
      }
      let bi = 0;

      const age = game.t / MATCH;
      for (const p of game.shots) {
        const team = TEAMS[p.team], len = p.trail.length;
        if (len > 1) {
          g.moveTo(p.trail[0][0], p.trail[0][1]);
          for (let j = 1; j < len; j++) g.lineTo(p.trail[j][0], p.trail[j][1]);
          if (p.kind === 2) { const rr = clamp(62 + Math.sqrt(p.value / 1e6) * 26, 62, 130); g.stroke({ width: rr * 1.7, color: team.hex, alpha: 0.32, cap: 'round', join: 'round' }); g.moveTo(p.trail[0][0], p.trail[0][1]); for (let j = 1; j < len; j++) g.lineTo(p.trail[j][0], p.trail[j][1]); g.stroke({ width: rr * .5, color: team.hex, alpha: 0.35, cap: 'round', join: 'round' }); }
          else if (p.kind === 3) g.stroke({ width: 2.4, color: team.hex, alpha: 0.65 });
          else if (age > .45 || p.kind === 4) g.stroke({ width: 1.2, color: 0xffffff, alpha: 0.28 });
          else g.stroke({ width: 1.5, color: 0xffffff, alpha: 0.22 });
        }
        if (p.kind === 2) {
          if (bi >= this.ballPool.length) continue;
          const r = clamp(62 + Math.sqrt(p.value / 1e6) * 26, 62, 130), B = this.ballPool[bi++];
          B.c.visible = true; B.c.x = p.x; B.c.y = p.y;
          B.glow.texture = this.teamGlowTex[p.team]; B.glow.width = B.glow.height = r * 3.4;
          const key = p.team + ':' + (r | 0);
          if (B.key !== key) { B.key = key; B.ball.clear().circle(0, 0, r).fill({ color: team.hex, alpha: .95 }).circle(0, 0, r * .82).fill({ color: 0x08121f, alpha: .93 }).circle(0, 0, r * .82).stroke({ width: 2, color: team.hex, alpha: 1 }).circle(0, 0, r).stroke({ width: 2.5, color: 0xffffff, alpha: .55 }); }
          const txt = fmt(p.value); if (B.label.text !== txt) B.label.text = txt;
          B.label.style.fontSize = clamp(r * .42, 18, 54);
        } else {
          // bright tip
          g.circle(p.x, p.y, p.kind === 3 ? 3.5 : 2.2).fill({ color: 0xffffff, alpha: 0.9 });
        }
      }
      for (; bi < this.ballPool.length; bi++) this.ballPool[bi].c.visible = false;
      // storm sweep: concentric dotted stream arcs + bright leading edge
      for (const w of game.waves) {
        const [bx, by] = BASES[w.team], tm = TEAMS[w.team];
        for (let j = 0; j < 4; j++) {
          const rr2 = w.r - j * 70; if (rr2 < 40) continue;
          const step = 11 / rr2, al = j === 0 ? .95 : .55 - j * .1;
          for (let a = w.a - w.half; a <= w.a + w.half; a += step) g.circle(bx + Math.cos(a) * rr2, by + Math.sin(a) * rr2, j === 0 ? 4.2 : 3);
          g.fill({ color: j === 0 ? 0xffffff : tm.hi ? ((tm.hi[0] << 16) | (tm.hi[1] << 8) | tm.hi[2]) : tm.hex, alpha: Math.min(1, al + .2) });
        }
        g.arc(bx, by, w.r, w.a - w.half, w.a + w.half).stroke({ width: 10, color: tm.hex, alpha: .35 });
      }
      // main beam per team: coloured energy ribbon from base along aim until it exits own turf + ~reach
      for (let t = 0; t < 4 && game.t > 2.5; t++) {
        const [bx, by] = BASES[t], a = game.aim[t], ca = Math.cos(a), sa = Math.sin(a);
        let L = 0; const maxL = 760;
        while (L < maxL) { const x = bx + ca * L, y = by + sa * L; if (x < 0 || y < 0 || x >= G || y >= G) break; const o = game.grid[((y / S) | 0) * GS + ((x / S) | 0)]; if (o < 4 && o !== t) break; L += 6; }
        const ex = bx + ca * L, ey = by + sa * L, hex = TEAMS[t].hex;
        g.moveTo(bx, by).lineTo(ex, ey).stroke({ width: 16, color: hex, alpha: 0.10 });
        g.moveTo(bx, by).lineTo(ex, ey).stroke({ width: 8, color: hex, alpha: 0.28 });
        g.moveTo(bx, by).lineTo(ex, ey).stroke({ width: 2.5, color: 0xffffff, alpha: 0.35 });
      }
      // ribbon trails
      for (const p of game.ribbons) {
        const len = p.trail.length; if (len < 2) continue;
        const alpha = Math.min(1, p.life * 1.8) * 0.32;
        g.moveTo(p.trail[0][0], p.trail[0][1]);
        for (let j = 1; j < len; j++) g.lineTo(p.trail[j][0], p.trail[j][1]);
        g.stroke({ width: 0.8, color: 0xffffff, alpha: alpha * 0.45 });
      }
    }

    drawBases(game) {
      const g = this.baseG; g.clear();
      const corner = [[.12, .12], [.88, .12], [.12, .88], [.88, .88]];
      for (let t = 0; t < 4; t++) {
        const team = TEAMS[t], [ux, uy] = corner[t];
        const x = AX + G * ux, y = AY + G * uy;
        const grow = clamp((game.t - .6) / 4.5, 0, 1), r = 20 + 72 * grow * grow * (3 - 2 * grow);
        const pulse = Math.sin(game.t * 2.4 + t) * 2.8;
        // outer glow disc
        if (game.flood === t) { g.circle(x, y, r + 26).fill({ color: team.hex, alpha: .9 }); g.circle(x, y, r + 34).stroke({ width: 8, color: 0xffffff, alpha: .8 }); }
        g.circle(x, y, r + 14).stroke({ width: 22, color: team.hex, alpha: 0.10 }); g.circle(x, y, r + 6).stroke({ width: 10, color: team.hex, alpha: 0.22 });
        g.circle(x, y, r + pulse * .4).stroke({ width: 4, color: team.hex, alpha: 1 }); g.circle(x, y, r + pulse * .4).stroke({ width: 1.2, color: 0xffffff, alpha: .7 });
        g.circle(x, y, r - 8).stroke({ width: 6, color: team.hex, alpha: 0.55 });
        g.circle(x, y, r - 6).fill({ color: 0x020812, alpha: 0.4 }); g.circle(x, y, r - 6).fill({ color: team.hex, alpha: 0.16 });
        // aim
        const a = game.aim[t];
        // rotating turret: hub + barrel that sticks out past the ring; streams follow this angle
        const ca = Math.cos(a), sa = Math.sin(a), px = -sa, py = ca, L0 = 6, L1 = r + 22, bw = 6;
        g.poly([x + ca * L0 + px * bw, y + sa * L0 + py * bw, x + ca * L1 + px * (bw * .7), y + sa * L1 + py * (bw * .7), x + ca * L1 - px * (bw * .7), y + sa * L1 - py * (bw * .7), x + ca * L0 - px * bw, y + sa * L0 - py * bw])
          .fill({ color: team.hex, alpha: .95 }).stroke({ width: 1.5, color: 0xffffff, alpha: .8 });
        g.moveTo(x + ca * L0, y + sa * L0).lineTo(x + ca * L1, y + sa * L1).stroke({ width: 1.6, color: 0xffffff, alpha: .9 });
        g.circle(x + ca * L1, y + sa * L1, 5).fill({ color: 0xffffff, alpha: .9 });
        g.circle(x, y - 3, 8).fill({ color: 0x07111c, alpha: 1 }).stroke({ width: 2.2, color: team.hex, alpha: 1 });
        g.circle(x, y - 3, 3).fill({ color: 0xffffff, alpha: 1 });

        const texts = this.baseTexts[t]; const ta = clamp((r - 55) / 30, 0, 1); texts.ammo.alpha = texts.sec.alpha = ta; texts.lab.alpha = texts.zero.alpha = 1 - ta; texts.lab.x = x; texts.lab.y = y - r - 4; texts.zero.x = x + r + 6; texts.zero.y = y;
        if (ta < 1) { g.circle(x, y, r).fill({ color: team.hex, alpha: .12 * (1 - ta) }); }
        // ref layout: [shield] 25.86M  /  hub  /  [gun box] 241,410
        texts.ammo.style.fontSize = 21; texts.ammo.text = fmt(game.ammo[t]); texts.ammo.x = x - 22; texts.ammo.y = y - 26; texts.ammo.style.fill = 0xffffff;
        const sx = x - 42, sy = y - 26; // shield icon
        if (ta > .3) g.poly([sx, sy - 9, sx + 8, sy - 6, sx + 7, sy + 3, sx, sy + 9, sx - 7, sy + 3, sx - 8, sy - 6]).stroke({ width: 1.6, color: 0xffffff, alpha: .85 });
        if (ta > .3) g.poly([sx, sy - 4, sx + 4, sy - 2.5, sx + 3.5, sy + 2, sx, sy + 4.5, sx - 3.5, sy + 2, sx - 4, sy - 2.5]).fill({ color: team.hex, alpha: 1 });
        const secondary = Math.max(1000, Math.round(120000 + game.share[t] * 1.2e6 + game.t * 900));
        if (ta > .3) g.roundRect(x - 72, y + 9, 144, 26, 4).fill({ color: 0x02060c, alpha: .55 }).stroke({ width: 1, color: 0xc8e6fa, alpha: .25 });
        const gx2 = x - 56, gy2 = y + 22; // gun icon
        if (ta > .3) g.rect(gx2 - 10, gy2 - 1.5, 20, 3).fill({ color: 0xffffff, alpha: .8 }); g.rect(gx2 - 4, gy2 + 1, 3, 4).fill({ color: 0xffffff, alpha: .8 });
        texts.sec.style.fontSize = 17; texts.sec.text = fmtScore(secondary); texts.sec.style.fill = team.hex === 0xffa514 ? 0xffe0b0 : 0xffffff;
        texts.sec.x = x + 8; texts.sec.y = y + 22;
      }
    }

    drawMeters(game) {
      const g = this.meterG; g.clear();
      const specs = [
        { x: 812, t: 0, y0: 40, i: 0 },
        { x: 812, t: 2, y0: 582, i: 1 },
        { x: 1894, t: 1, y0: 40, i: 2 },
        { x: 1894, t: 3, y0: 582, i: 3 }
      ];
      for (const { x, t, y0, i } of specs) {
        const team = TEAMS[t], h = 458, share = game.share[t], top = y0 < 500, dir = top ? 1 : -1;
        const Y = (d) => top ? y0 + d : y0 + h - d; // distance from the outer end of the strip
        g.rect(x - 22, y0 - 26, 46, h + 52).fill({ color: 0x040c16, alpha: 0.92 });
        const bY = Y(78), rS = Y(108), rE = Y(h - 6);
        g.moveTo(x + 1.5, rS).lineTo(x + 1.5, rE).stroke({ width: 1.2, color: team.hex, alpha: .55 });
        for (let q = 0; q <= 3; q++) {
          const yy = rS + (rE - rS) * q / 4;
          g.circle(x + 1.5, yy, 3.2).stroke({ width: 1, color: team.hex, alpha: .8 }); g.circle(x + 1.5, yy, 1.2).fill({ color: team.hex, alpha: 1 });
          g.moveTo(x - 4, yy).lineTo(x + 7, yy).stroke({ width: .8, color: team.hex, alpha: .6 });
        }
        // glowing fill grows from the far end toward the badge
        const fl = Math.max(4, share * (rE - rS) * dir) * dir, f0 = rE, f1 = rE - fl;
        g.moveTo(x + 1.5, f0).lineTo(x + 1.5, f1).stroke({ width: 7, color: team.hex, alpha: .25 });
        g.moveTo(x + 1.5, f0).lineTo(x + 1.5, f1).stroke({ width: 3, color: team.hex, alpha: 1 });
        g.moveTo(x + 1.5, f0).lineTo(x + 1.5, f1).stroke({ width: 1, color: 0xffffff, alpha: .85 });
        // badge: glow + crosshair ring
        g.circle(x + 1.5, bY, 22).fill({ color: team.hex, alpha: .14 });
        g.circle(x + 1.5, bY, 17).stroke({ width: 2.2, color: team.hex, alpha: 1 });
        for (let k = 0; k < 4; k++) { const an = k * Math.PI / 2; g.moveTo(x + 1.5 + Math.cos(an) * 19, bY + Math.sin(an) * 19).lineTo(x + 1.5 + Math.cos(an) * 24, bY + Math.sin(an) * 24); }
        g.stroke({ width: 1.4, color: team.hex, alpha: .9 });
        g.circle(x + 1.5, bY, 12).fill({ color: 0x061018, alpha: 1 }).stroke({ width: 1.2, color: 0xffffff, alpha: .6 });
        const mt = this.meterTexts[i];
        mt.pct.text = (share * 100).toFixed(2) + '%'; mt.pct.style.fill = team.hex; mt.pct.style.fontSize = 15;
        mt.pct.anchor.set(.5, .5); mt.pct.x = x + 1.5; mt.pct.y = Y(-14);
        mt.n.text = '' + Math.round(share * 800); mt.n.x = x + 1.5; mt.n.y = Y(6);
        mt.of.x = x + 1.5; mt.of.y = Y(22);
        mt.ex.x = x + 1.5; mt.ex.y = Y(48);
        mt.full.x = x + 1.5; mt.full.y = Y(105) + dir * 0;
        mt.full.y = bY + dir * 30;
        mt.ticks.forEach((o, k) => { o.x = x - 12; o.y = rS + (rE - rS) * (k + 1) / 4; });
        mt.lv.text = '' + game.level[t]; mt.lv.x = x + 1.5; mt.lv.y = bY;
      }
    }

    render(game) {
      // left
      if ((game.frame & 1) === 0 || !this._leftOnce) { drawLeftTo(this.leftCtx, game); this.leftTex.source.update(); this._leftOnce = true; }

      this.drawStars(game);
      if (game.dirty && (game.terrainAge === 0 || game.frame - game.terrainAge >= 10)) this.rebuildTerrain(game);
      this.updateFoamRT();

      this.syncSilk(game);
      this.drawShots(game);
      this.syncSparks(game);
      this.drawBases(game);
      this.drawMeters(game);

      this.pauseG.visible = game.paused;
      this.pauseTxt.visible = game.paused;
      if (game.paused) {
        this.pauseG.clear().rect(0, 0, W, H).fill({ color: 0x02050b, alpha: 0.74 });
      }
    }
  }

  /* ===================== BOOT ===================== */
  let app, view, game = null, preview = null, playing = false, last = 0;
  const clock = { acc: 0 };

  function showStart() {
    overlay.classList.remove('hidden');
    startpanel.classList.remove('hidden');
    endpanel.classList.add('hidden');
    overlay.style.display = 'grid';
    document.getElementById('shareLabel').textContent = '等待开战';
    document.getElementById('timer').textContent = '00:00';
  }
  function fit() {
    const r = Math.min(innerWidth / W, innerHeight / H);
    canvas.style.width = (W * r) + 'px';
    canvas.style.height = (H * r) + 'px';
  }
  function pos(e) {
    const r = canvas.getBoundingClientRect();
    return { x: (e.clientX - r.left) * W / r.width, y: (e.clientY - r.top) * H / r.height };
  }
  function aimAt(p) {
    if (!game || !playing) return;
    const [bx, by] = BASES[game.player];
    game.playerAim = Math.atan2(p.y - (AY + by), p.x - (AX + bx));
  }

  function start(t) {
    t = ((t | 0) % 4 + 4) % 4;
    playing = true;
    overlay.classList.remove('shown');
    game = new Game(t);
    preview = null;
    game.autoAim = document.getElementById('autoAim').checked;
    game.playerAim = game.aim[t];
    overlay.classList.add('hidden');
    startpanel.classList.add('hidden');
    endpanel.classList.add('hidden');
    last = performance.now(); clock.acc = 0;
    document.getElementById('timer').textContent = '00:00';
    document.getElementById('shareLabel').textContent = TEAMS[t].name + ' 0.0%';
    // force terrain rebuild
    const warp = +(new URLSearchParams(location.search).get('warp') || 0);
    for (let i = 0; i < warp * 60; i++) game.tick(1 / 60);
    if (view) view.rebuildTerrain(game);
  }
  function sync() {
    if (!game || !playing) return;
    const elapsed = Math.max(0, Math.floor(game.t | 0));
    const m = Math.floor(elapsed / 60), s = elapsed % 60;
    document.getElementById('timer').textContent = String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    document.getElementById('shareLabel').textContent = TEAMS[game.player].name + ' ' + (game.share[game.player] * 100).toFixed(1) + '%';
  }
  function finish() {
    playing = false;
    overlay.classList.remove('hidden');
    overlay.style.display = 'grid';
    startpanel.classList.add('hidden');
    endpanel.classList.remove('hidden');
    document.getElementById('endMsg').textContent = `${TEAMS[game.winner].name} 获胜 · 占领 ${(game.share[game.winner] * 100).toFixed(1)}%`;
  }
  function ensurePreview() {
    if (!preview) { preview = new Game(0); preview.autoFire = false; preview.paused = true; }
    return preview;
  }

  async function boot() {
    if (!window.PIXI) throw new Error('PIXI missing');
    app = new PIXI.Application();
    await app.init({
      canvas,
      width: W,
      height: H,
      background: '#030811',
      antialias: true,
      preference: 'webgl',
      autoDensity: false,
      resolution: 1,
      powerPreference: 'high-performance'
    });
    view = new PixiView(app);
    window.__W4B_APP = app;
    window.__W4B_VIEW = view;
    window.__W4B_ENGINE = 'pixi-v8-webgl';

    addEventListener('resize', fit); fit();

    canvas.addEventListener('pointerdown', e => {
      if (!playing || !game || game.over) return;
      canvas.setPointerCapture(e.pointerId);
      const p = pos(e);
      if (p.x < LEFT && p.y > ITEMY && p.y < ITEMY + ITEMH) {
        const i = clamp(Math.floor(p.x / (LEFT / 5)), 0, 4); game.use(game.player, i); return;
      }
      if (p.x >= AX && p.x <= AX + G && p.y >= AY && p.y <= AY + G) {
        if (!game.autoAim) aimAt(p); game.firing = true;
      }
    });
    canvas.addEventListener('pointermove', e => { if (game && playing && !game.autoAim) aimAt(pos(e)); });
    canvas.addEventListener('pointerup', () => { if (game) game.firing = false; });
    canvas.addEventListener('pointercancel', () => { if (game) game.firing = false; });
    document.getElementById('autoAim').addEventListener('change', e => { if (game) game.autoAim = e.target.checked; });
    document.getElementById('btnPause').addEventListener('click', () => { if (game && playing) game.paused = !game.paused; });
    document.getElementById('btnRestart').addEventListener('click', () => { if (playing && game) start(game.player); else showStart(); });
    document.getElementById('btnAgain').addEventListener('click', () => { playing = false; showStart(); });
    document.querySelectorAll('.color-btn').forEach(b => b.addEventListener('click', ev => { ev.preventDefault(); ev.stopPropagation(); start(+b.dataset.team); }));
    const quick = document.getElementById('btnQuick');
    if (quick) quick.addEventListener('click', () => start(0));
    addEventListener('keydown', e => {
      if (!playing) { if (e.key >= '1' && e.key <= '4') { start(+e.key - 1); e.preventDefault(); } return; }
      if (!game) return;
      if (e.key === ' ') { game.paused = !game.paused; e.preventDefault(); }
      const n = +e.key; if (n >= 1 && n <= 5) game.use(game.player, n - 1);
    });

    showStart();
    last = performance.now();
    const STEP = 1 / 60;
    app.ticker.add(() => {
      const now = performance.now();
      let frameDt = Math.max(0, (now - last) / 1000); last = now;
      // catch up sim to wall clock (render may be slow on software WebGL)
      clock.acc = Math.min(0.5, clock.acc + frameDt);
      if (playing && game) {
        window.__W4B = game;
        let steps = 0;
        const pt0 = performance.now();
        while (clock.acc >= STEP && steps < 24) { game.tick(STEP); clock.acc -= STEP; steps++; }
        const pt1 = performance.now();
        view.render(game);
        const pt2 = performance.now();
        const P = window.__W4B_PERF || (window.__W4B_PERF = { tickMs: 0, renderMs: 0, steps: 0 });
        P.tickMs = P.tickMs * .9 + ((pt1 - pt0) / Math.max(1, steps)) * .1; P.renderMs = P.renderMs * .9 + (pt2 - pt1) * .1; P.steps = steps;
        sync();
        if (game.over && !overlay.classList.contains('shown')) { finish(); overlay.classList.add('shown'); }
      } else {
        if (overlay.classList.contains('hidden')) showStart();
        const p = ensurePreview();
        p.paused = false; p.autoFire = true;
        let steps = 0;
        while (clock.acc >= STEP && steps < 4) { p.tick(STEP); clock.acc -= STEP; steps++; }
        p.paused = true;
        view.render(p);
        window.__W4B = p;
      }
    });
  }

  boot().catch(err => {
    console.error(err);
    const msg = document.createElement('div');
    msg.style.cssText = 'position:fixed;inset:0;display:grid;place-items:center;background:#030811;color:#fff;z-index:99999;font:16px sans-serif;padding:24px;text-align:center';
    msg.textContent = 'WebGL / Pixi 初始化失败：' + (err && err.message ? err.message : err);
    document.body.appendChild(msg);
  });
})();
