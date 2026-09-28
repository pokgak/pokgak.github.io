// Discrete-event model of a hot-row lock convoy with MultiXact SLRU contention.
// Deliberately small: one hot row, one parent row, one SLRU LWLock, one
// connection budget. Times are in seconds.
(function (root) {
  const MEMBERS_PER_PAGE = 1636; // MULTIXACT_MEMBERS_PER_PAGE for 8 KB pages

  const DEFAULTS = {
    concA: 100,          // priority queue max concurrent dispatches
    concB: 0,            // second queue max concurrent dispatches
    hotShare: 0.75,      // fraction of tasks that hit the hot row
    holdMs: 2,           // work while holding the hot row lock
    fkLookups: 3,        // MultiXact lookups while holding the row lock
    coldMs: 40,          // duration of a task on a cold row
    slruBuffers: 16,     // PG15 NUM_MULTIXACTMEMBER_BUFFERS
    hitMs: 0.01,         // SLRU access served from cache
    missMs: 1,           // SLRU access that has to read and evict a page
    thrash: 0.004,       // extra cost per LWLock waiter (wakeups, retries)
    lockTimeoutMs: 0,    // 0 = off. Only covers the heavyweight row lock wait.
    retryBackoffS: 1,    // Cloud Tasks waits before retrying a failed task
    apiRate: 250,        // API requests/s, each reads the parent row
    apiLookups: 4,       // MultiXact lookups per API request (tuple versions checked)
    apiMs: 3,
    clientTimeoutS: 10,  // API client gives up and retries; server keeps going
    maxRetries: 2,
    maxConnections: 1000,
    seed: 1,
  };

  class Heap {
    constructor() { this.a = []; }
    get size() { return this.a.length; }
    push(e) {
      const a = this.a; a.push(e);
      let i = a.length - 1;
      while (i > 0) {
        const p = (i - 1) >> 1;
        if (a[p].t <= e.t) break;
        a[i] = a[p]; i = p;
      }
      a[i] = e;
    }
    peek() { return this.a[0]; }
    pop() {
      const a = this.a, top = a[0], last = a.pop();
      if (a.length) {
        let i = 0;
        for (;;) {
          const l = 2 * i + 1, r = l + 1;
          let m = i;
          const mt = () => (m === i ? last.t : a[m].t);
          if (l < a.length && a[l].t < mt()) m = l;
          if (r < a.length && a[r].t < mt()) m = r;
          if (m === i) break;
          a[i] = a[m]; i = m;
        }
        a[i] = last;
      }
      return top;
    }
  }

  function rng(seed) {
    let s = seed >>> 0 || 1;
    return () => {
      s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0;
      return s / 4294967296;
    };
  }

  function createSim(overrides) {
    const P = Object.assign({}, DEFAULTS, overrides);
    const rand = rng(P.seed);
    let ev = new Heap();
    let now = 0;
    let downUntil = -1;

    // Slot states, used by the diagram.
    // idle, cold, fk (joining MultiXact), rowwait, hold, noconn
    let slots = [];
    let conns = 0;
    let apiConns = 0;

    let row = { holder: null, queue: [] };
    let members = 0;             // live lockers on the parent row = MultiXact size
    let mlog = [];             // [time, size] for every MultiXact created
    let mlogStart = 0;           // index of first entry still inside any horizon
    let prefix = [0];            // prefix sums of sizes over mlog
    let pinAt = null;            // start of the long-running transaction
    let horizon = 0, horizonAt = -1;

    let slru = { busy: false, queue: [], hits: 0, misses: 0 };

    const win = freshWindow();
    let lastWindow = null;

    function freshWindow() {
      return { start: now, hot: 0, cold: 0, aborts: 0, api: 0, apiErr: 0, apiLat: [], cpu: 0, hits: 0, misses: 0 };
    }

    function at(t, fn) { ev.push({ t, fn }); }

    // --- slots / dispatch ---

    function resizeSlots() {
      const want = P.concA + P.concB;
      while (slots.length < want) {
        const s = { id: slots.length, q: slots.length < P.concA ? 'A' : 'B', state: 'idle', txn: null };
        slots.push(s);
        at(now + rand() * 0.01, () => dispatch(s));
      }
      for (const s of slots) s.q = s.id < P.concA ? 'A' : 'B';
      for (let i = want; i < slots.length; i++) slots[i].retired = true;
      for (let i = 0; i < want; i++) {
        if (slots[i].retired) {
          slots[i].retired = false;
          if (slots[i].state === 'idle') at(now, () => dispatch(slots[i]));
        }
      }
      while (slots.length > want && slots[slots.length - 1].state === 'idle') slots.pop();
    }

    function dispatch(s) {
      if (s.retired) {
        s.state = 'idle';
        while (slots.length && slots[slots.length - 1].retired && slots[slots.length - 1].state === 'idle') slots.pop();
        return;
      }
      if (now < downUntil || conns >= P.maxConnections) {
        s.state = 'noconn';
        at(now + 0.1, () => dispatch(s));
        return;
      }
      conns++;
      const txn = { slot: s, start: now, hot: rand() < P.hotShare, alive: true };
      s.txn = txn;
      if (txn.hot) {
        s.state = 'fk';
        members++;
        recordMulti(members);
        slruAccess(txn, true, () => requestRow(txn));
      } else {
        s.state = 'cold';
        at(now + P.coldMs / 1000, () => {
          win.cpu += 0.001;
          win.cold++;
          finish(txn);
        });
      }
    }

    function finish(txn, backoff = 0) {
      txn.alive = false;
      if (txn.hot) members--;
      conns--;
      const s = txn.slot;
      s.txn = null;
      s.state = backoff ? 'backoff' : 'idle';
      at(now + backoff, () => dispatch(s));
    }

    // --- hot row lock ---

    function requestRow(txn) {
      if (!row.holder) return grant(txn);
      txn.slot.state = 'rowwait';
      txn.waitSince = now;
      row.queue.push(txn);
      if (P.lockTimeoutMs > 0) {
        at(now + P.lockTimeoutMs / 1000, () => {
          if (!txn.alive || txn.granted) return;
          const i = row.queue.indexOf(txn);
          if (i >= 0) row.queue.splice(i, 1);
          win.aborts++;
          finish(txn, P.retryBackoffS);
        });
      }
    }

    function grant(txn) {
      txn.granted = true;
      row.holder = txn;
      txn.slot.state = 'hold';
      at(now + P.holdMs / 1000, () => {
        win.cpu += 0.0005;
        lookups(txn, P.fkLookups);
      });
    }

    function lookups(txn, n) {
      if (n === 0) return commit(txn);
      slruAccess(txn, false, () => lookups(txn, n - 1));
    }

    function commit(txn) {
      win.hot++;
      row.holder = null;
      finish(txn);
      while (row.queue.length) {
        const next = row.queue.shift();
        if (next.alive) { grant(next); break; }
      }
    }

    // --- MultiXact bookkeeping ---

    function recordMulti(size) {
      mlog.push([now, size]);
      prefix.push(prefix[prefix.length - 1] + size);
    }

    function oldestTxnStart() {
      let t = now;
      for (const s of slots) if (s.txn && s.txn.start < t) t = s.txn.start;
      if (pinAt !== null && pinAt < t) t = pinAt;
      return t;
    }

    // Members written since the oldest running transaction started. Lookups
    // of MultiXacts older than that horizon are answered without reading the
    // SLRU, so this is the working set the cache has to hold.
    function workingSet() {
      if (now - horizonAt > 0.05) {
        horizon = oldestTxnStart();
        horizonAt = now;
        compact();
      }
      let lo = mlogStart, hi = mlog.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (mlog[mid][0] < horizon) lo = mid + 1; else hi = mid;
      }
      return prefix[mlog.length] - prefix[lo];
    }

    function compact() {
      while (mlogStart < mlog.length && mlog[mlogStart][0] < horizon) mlogStart++;
      if (mlogStart > 50000) {
        mlog.splice(0, mlogStart);
        const base = prefix[mlogStart];
        prefix = prefix.slice(mlogStart).map(v => v - base);
        mlogStart = 0;
      }
    }

    function cacheMembers() { return P.slruBuffers * MEMBERS_PER_PAGE; }

    function missProb() {
      const w = workingSet();
      return w <= cacheMembers() ? 0 : 1 - cacheMembers() / w;
    }

    // --- SLRU LWLock: one FIFO server ---

    function slruAccess(owner, write, done) {
      slru.queue.push({ owner, write, done });
      if (!slru.busy) slruNext();
    }

    function slruNext() {
      const req = slru.queue.shift();
      if (!req) { slru.busy = false; return; }
      slru.busy = true;
      const miss = rand() < missProb();
      if (miss) { slru.misses++; win.misses++; } else { slru.hits++; win.hits++; win.cpu += P.hitMs / 1000; }
      const base = (miss ? P.missMs : P.hitMs) / 1000;
      const cost = base * (1 + P.thrash * Math.min(slru.queue.length, 2000));
      at(now + cost, () => { req.done(); slruNext(); });
    }

    // --- API traffic ---

    function scheduleApi() {
      if (P.apiRate <= 0) { at(now + 0.1, scheduleApi); return; }
      at(now - Math.log(1 - rand()) / P.apiRate, () => { apiRequest(0, now); scheduleApi(); });
    }

    function apiRequest(attempt, firstStart) {
      win.api++;
      const client = { done: false };
      const retry = () => {
        win.apiErr++;
        if (attempt < P.maxRetries) at(now + 0.2 + rand() * 0.3, () => apiRequest(attempt + 1, firstStart));
        else win.apiLat.push(now - firstStart);
      };
      if (now < downUntil || conns >= P.maxConnections) { retry(); return; }
      conns++; apiConns++;
      at(now + P.clientTimeoutS, () => {
        if (client.done) return;
        client.done = true;
        retry();
      });
      apiLookups(P.apiLookups, () => {
        at(now + P.apiMs / 1000, () => {
          win.cpu += 0.0005;
          conns--; apiConns--;
          if (client.done) return;
          client.done = true;
          win.apiLat.push(now - firstStart);
        });
      });
    }

    function apiLookups(n, done) {
      if (n === 0) return done();
      slruAccess(null, false, () => apiLookups(n - 1, done));
    }

    // --- public API ---

    function closeWindow() {
      const w = win, dur = Math.max(now - w.start, 1e-9);
      const lat = w.apiLat.slice().sort((a, b) => a - b);
      const p95 = lat.length ? lat[Math.min(lat.length - 1, Math.floor(lat.length * 0.95))] : 0;
      lastWindow = {
        t: now,
        hotPerS: w.hot / dur,
        coldPerS: w.cold / dur,
        abortsPerS: w.aborts / dur,
        apiErrPct: w.api ? Math.min(100, (100 * w.apiErr) / w.api) : 0,
        apiPerS: w.api / dur,
        apiP95: p95,
        cpuPct: Math.min(100, (100 * w.cpu) / (16 * dur)),
        missPct: w.hits + w.misses ? (100 * w.misses) / (w.hits + w.misses) : 0,
      };
      Object.assign(win, freshWindow());
      return lastWindow;
    }

    function run(until) {
      while (ev.size && ev.peek().t <= until) {
        const e = ev.pop();
        now = e.t;
        e.fn();
      }
      now = until;
    }

    function snapshot() {
      const counts = { idle: 0, cold: 0, fk: 0, rowwait: 0, hold: 0, noconn: 0, backoff: 0 };
      for (const s of slots) counts[s.state]++;
      return {
        t: now,
        slots: slots.map(s => [s.q, s.state]),
        counts,
        members,
        rowQueue: row.queue.length,
        workingSet: workingSet(),
        cacheMembers: cacheMembers(),
        slruQueue: slru.queue.length,
        conns,
        apiConns,
        workerConns: conns - apiConns - (pinAt !== null ? 1 : 0),
        maxConnections: P.maxConnections,
        pinned: pinAt !== null,
        down: now < downUntil,
        pinAge: pinAt !== null ? now - pinAt : 0,
      };
    }

    function set(k, v) {
      P[k] = v;
      if (k === 'concA' || k === 'concB') resizeSlots();
    }

    // Drop every session, lock and queue, like a DB restart. Clients keep
    // arriving and fail until the DB is back.
    function restart(downS = 2) {
      ev = new Heap();
      slots = []; conns = 0; apiConns = 0;
      row = { holder: null, queue: [] };
      members = 0; mlog = []; mlogStart = 0; prefix = [0];
      pinAt = null; horizonAt = -1;
      slru = { busy: false, queue: [], hits: 0, misses: 0 };
      downUntil = now + downS;
      resizeSlots();
      scheduleApi();
    }

    function pin() { if (pinAt === null) { pinAt = now; conns++; horizonAt = -1; } }
    function unpin() { if (pinAt !== null) { pinAt = null; conns--; horizonAt = -1; } }

    resizeSlots();
    scheduleApi();

    return { run, snapshot, closeWindow, set, pin, unpin, restart, params: P, get now() { return now; } };
  }

  const api = { createSim, DEFAULTS, MEMBERS_PER_PAGE };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PgHotRowSim = api;
})(typeof window !== 'undefined' ? window : globalThis);
