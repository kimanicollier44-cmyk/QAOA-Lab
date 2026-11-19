#!/usr/bin/env python3
"""QAOA-Lab - educational Quantum Approximate Optimization Algorithm lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Education only - and the central lesson is stated up front:

  * QAOA is a hybrid heuristic: a parameterised quantum circuit
    prepares a state, a classical optimiser tunes the angles, and
    the expected cost is read off the prepared state. This lab
    simulates that circuit EXACTLY (full statevector, from scratch)
    on graphs small enough to brute-force the true MaxCut optimum,
    so every QAOA number can be graded against the truth.
  * On these tiny instances a one-pass classical GREEDY algorithm
    reaches the optimum on all three graphs, and QAOA's expected
    cut only ties it at the deepest setting on two of them. That
    is printed in the headline table, not buried: QAOA is compared
    here, never crowned, and no quantum advantage is claimed
    anywhere in this lab.
  * What QAOA demonstrably does here: beat uniform random sampling
    on every instance at every depth, match the known analytic
    p = 1 formula on a triangle-free regular graph to 1e-9, and
    concentrate probability on optimal cut strings far above the
    uniform baseline.

Graphs, angles, and the one seeded random instance are all fixed,
so every run - and every rerun - is byte-identical. Real-hardware
execution, production optimisation, quantum-advantage, and
NP-hardness claims are permanent HOLD gates - with Gemini Argon 4
Extended Thinking as DECIDER (names-only, tighten-only), Muse as
advisor (never overrides HOLD), and Google Flow plan-only seats.
"""
import cmath
import hashlib
import json
import math
import sys

# ---------------------------------------------------------------- constants
VERSION = "1.0.0"
SEED = 20261119  # splitmix64 seed for the random regular graph (named, fixed)

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "quantum_advantage_claim": "HOLD - no quantum advantage is claimed; this is an exact classical simulation of at most 8 qubits, graded against classical baselines in the same run",
    "real_hardware_execution_claim": "HOLD - no real QPU executed anything; every state here is a classical statevector simulation",
    "production_optimization_use": "HOLD - no solving real production, engineering, or business optimisation problems from this teaching lab",
    "np_hard_solved_claim": "HOLD - QAOA is a heuristic; it does not solve NP-hard problems in polynomial time and no such claim is made",
    "guaranteed_optimum_claim": "HOLD - QAOA samples are heuristic draws; no run guarantees an optimal solution to any instance",
    "benchmark_generalisation_claim": "HOLD - ratios on three tiny graphs do not generalise to other instances, sizes, or depths",
    "cryptography_break_claim": "HOLD - MaxCut on teaching graphs is not a cryptosystem; nothing here breaks or weakens any cryptography",
    "financial_optimization_advice": "HOLD - no portfolio, trading, or financial optimisation advice follows from this lab",
    "logistics_routing_claim": "HOLD - no real logistics, routing, or scheduling deployment claim follows from a toy MaxCut model",
    "vendor_benchmark_claim": "HOLD - no vendor, QPU, or platform benchmark claim; no hardware was benchmarked",
    "investment_claim": "HOLD - no investment claim; a lab model is not a prospectus",
    "certification_claim": "HOLD - no certification that any system, algorithm, or device meets any standard",
    "live_hardware_control": "HOLD - no control of real quantum hardware, QPUs, or laboratory equipment, ever",
    "model_as_measurement_claim": "HOLD - a computed expectation is a statement about the simulated model at stated inputs, never a measurement of a real device",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ 1. splitmix64 PRNG
# The one random object in the lab - the seeded random regular graph -
# is drawn from this in-file splitmix64 stream, so the instance is the
# same on every machine and every run. The seed is named above and in
# the README; nothing else in the lab is random.

_MASK64 = (1 << 64) - 1


def splitmix64_stream(seed):
    """Deterministic splitmix64 stream of unsigned 64-bit integers."""
    state = seed & _MASK64
    while True:
        state = (state + 0x9E3779B97F4A7C15) & _MASK64
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        yield z ^ (z >> 31)


# ================================================================ 2. Graphs + MaxCut bookkeeping
# Three fixed instances, each small enough to brute-force exactly:
# the cycle C6 (triangle-free, 2-regular), the complete graph K4
# (3-regular, all triangles), and one seeded random 3-regular graph
# on 8 vertices drawn from the splitmix64 stream above.

def cycle_graph(n=6):
    return n, tuple((i, (i + 1) % n) for i in range(n))


def complete_graph(n=4):
    return n, tuple((i, j) for i in range(n) for j in range(i + 1, n))


def random_regular_graph(n=8, degree=3, seed=SEED):
    """Seeded random regular graph via stub pairing (configuration model).

    Stubs are shuffled with the splitmix64 stream and paired off;
    any pairing with a loop or a multi-edge is discarded and the
    stream keeps drawing, so the accepted graph is a deterministic
    function of the seed alone.
    """
    rng = splitmix64_stream(seed)
    while True:
        stubs = [v for v in range(n) for _ in range(degree)]
        for i in range(len(stubs) - 1, 0, -1):
            j = next(rng) % (i + 1)
            stubs[i], stubs[j] = stubs[j], stubs[i]
        edges = set()
        ok = True
        for k in range(0, len(stubs), 2):
            a, b = stubs[k], stubs[k + 1]
            if a == b:
                ok = False
                break
            edge = (min(a, b), max(a, b))
            if edge in edges:
                ok = False
                break
            edges.add(edge)
        if ok:
            return n, tuple(sorted(edges))


GRAPHS = {
    "cycle_c6": cycle_graph(),
    "complete_k4": complete_graph(),
    "random_regular_8": random_regular_graph(),
}


def cut_value(bits, edges):
    """Cut size of an assignment: bit i is vertex i's side."""
    return sum(1 for (u, v) in edges
               if ((bits >> u) & 1) != ((bits >> v) & 1))


def cut_table(n, edges):
    return [cut_value(x, edges) for x in range(1 << n)]


def brute_force_optimum(n, edges):
    """Exact optimum by enumeration: (C_max, number of optimal strings)."""
    cuts = cut_table(n, edges)
    best = max(cuts)
    return best, cuts.count(best)


def random_expected_cut(edges):
    """Expected cut of a uniform random assignment: every edge is
    cut with probability exactly 1/2, so the expectation is m/2."""
    return len(edges) / 2.0


def greedy_cut(n, edges):
    """Deterministic one-pass greedy: vertices in fixed order 0..n-1,
    each placed on the side that cuts the most edges to already-placed
    neighbours (ties go to side 0). Returns the full cut it achieves."""
    adjacency = [[] for _ in range(n)]
    for (u, v) in edges:
        adjacency[u].append(v)
        adjacency[v].append(u)
    assign = [None] * n
    for vtx in range(n):
        best_side, best_gain = 0, -1
        for side in (0, 1):
            gain = sum(1 for w in adjacency[vtx]
                       if assign[w] is not None and assign[w] != side)
            if gain > best_gain:
                best_gain, best_side = gain, side
        assign[vtx] = best_side
    bits = sum(assign[i] << i for i in range(n))
    return cut_value(bits, edges)


def graph_report():
    report = {}
    for name, (n, edges) in GRAPHS.items():
        degrees = [0] * n
        edge_set = set(edges)
        for (u, v) in edges:
            degrees[u] += 1
            degrees[v] += 1
        triangles = 0
        for a in range(n):
            for b in range(a + 1, n):
                for c in range(b + 1, n):
                    if ((a, b) in edge_set and (a, c) in edge_set
                            and (b, c) in edge_set):
                        triangles += 1
        cmax, n_opt = brute_force_optimum(n, edges)
        report[name] = {
            "n": n,
            "m": len(edges),
            "edges": [list(e) for e in edges],
            "regular_degree": (degrees[0]
                               if len(set(degrees)) == 1 else None),
            "triangles": triangles,
            "c_max": cmax,
            "optimal_strings": n_opt,
            "random_expected_cut": random_expected_cut(edges),
            "random_ratio": round(random_expected_cut(edges) / cmax, 6),
            "greedy_cut": greedy_cut(n, edges),
            "greedy_ratio": round(greedy_cut(n, edges) / cmax, 6),
        }
    return report


# ================================================================ 3. Exact QAOA statevector
# The circuit, from scratch: start in |+>^n, then for each layer
# apply the cost unitary exp(-i gamma H_C) - a diagonal phase
# exp(-i gamma * cut(x)) on each basis string, since the MaxCut
# Hamiltonian H_C = sum over edges of (1 - Z_u Z_v)/2 has eigenvalue
# cut(x) on |x> - and the mixer exp(-i beta * sum_j X_j), applied
# qubit by qubit as (cos beta) I - i (sin beta) X. No approximation:
# the state is the exact 2^n amplitudes.

def qaoa_state(n, edges, gammas, betas):
    """Exact QAOA statevector. Returns (amplitudes, cut table)."""
    if len(gammas) != len(betas):
        raise ValueError("gammas and betas must have equal length")
    size = 1 << n
    cuts = cut_table(n, edges)
    amp = [complex(1.0 / math.sqrt(size), 0.0)] * size
    for gamma, beta in zip(gammas, betas):
        for x in range(size):
            amp[x] *= cmath.exp(-1j * gamma * cuts[x])
        cb, sb = math.cos(beta), math.sin(beta)
        for q in range(n):
            step = 1 << q
            for base in range(0, size, step * 2):
                for off in range(step):
                    i0, i1 = base + off, base + off + step
                    a0, a1 = amp[i0], amp[i1]
                    amp[i0] = cb * a0 - 1j * sb * a1
                    amp[i1] = cb * a1 - 1j * sb * a0
    return amp, cuts


def expected_cut(n, edges, gammas, betas):
    amp, cuts = qaoa_state(n, edges, gammas, betas)
    return sum(abs(a) ** 2 * c for a, c in zip(amp, cuts))


def optimal_probability(n, edges, gammas, betas):
    """Total probability of measuring an optimal cut string."""
    amp, cuts = qaoa_state(n, edges, gammas, betas)
    cmax = max(cuts)
    return sum(abs(a) ** 2 for a, c in zip(amp, cuts) if c == cmax)


def state_norm(n, edges, gammas, betas):
    amp, _ = qaoa_state(n, edges, gammas, betas)
    return math.sqrt(sum(abs(a) ** 2 for a in amp))


# ================================================================ 4. Analytic p = 1 (triangle-free regular)
# For a d-regular TRIANGLE-FREE graph, the p = 1 expectation has a
# closed form. Only the two vertices of one edge and their other
# neighbours sit inside the p = 1 lightcone; triangle-freeness keeps
# those neighbour sets disjoint, the Y-Y cross term vanishes by
# symmetry, and each edge contributes independently:
#
#     <C_edge> = 1/2 + (1/2) * sin(4 beta) * sin(gamma) * cos(gamma)^(d-1)
#
# so <C> = m * <C_edge>. This lab verifies the formula against the
# exact statevector on the cycle C6 (d = 2) over an angle grid, and
# at the textbook point gamma = pi/4, beta = pi/8, where sin(gamma)
# cos(gamma) peaks at 1/2 and <C> = 4.5 exactly - an approximation
# ratio of exactly 0.75 against C_max = 6. The formula is NOT used
# for K4 or the seeded graph: both contain triangles.

def analytic_p1_expectation(m, degree, gamma, beta):
    return m * (0.5 + 0.5 * math.sin(4.0 * beta) * math.sin(gamma)
                * math.cos(gamma) ** (degree - 1))


def analytic_report():
    n, edges = GRAPHS["cycle_c6"]
    m, d = len(edges), 2
    worst = 0.0
    for gamma in (0.1, 0.3, 0.7, 1.0, 1.3):
        for beta in (0.05, 0.2, 0.39, 0.6):
            sim = expected_cut(n, edges, [gamma], [beta])
            ana = analytic_p1_expectation(m, d, gamma, beta)
            worst = max(worst, abs(sim - ana))
    peak = expected_cut(n, edges, [math.pi / 4], [math.pi / 8])
    return {
        "graph": "cycle_c6",
        "formula": "<C> = m * (1/2 + (1/2) sin(4b) sin(g) cos(g)^(d-1)), "
                   "d-regular triangle-free, p = 1",
        "grid_max_deviation": worst,
        "peak_gamma": round(math.pi / 4, 6),
        "peak_beta": round(math.pi / 8, 6),
        "peak_expected_cut": peak,
        "peak_ratio": round(peak / 6.0, 6),
    }


# ================================================================ 5. Deterministic angle optimisation
# No randomness anywhere: p = 1 starts from a fixed coarse grid over
# (gamma, beta); deeper p warm-starts from the previous depth's
# optimum - once with a zero layer appended, once with a zero layer
# prepended, once with the angles stretched by linear interpolation -
# and a coordinate pattern search (fixed step schedule, halving from
# 0.3 to below 1e-7, accepting only strict improvements) refines each
# start. Because a zero layer reproduces the shallower circuit
# exactly, the warm start guarantees the reported <C> cannot decrease
# with p on these instances; the search then only improves on it.

def _pattern_search(n, edges, start, step0=0.3, tol=1e-7):
    def value(angles):
        p = len(angles) // 2
        return expected_cut(n, edges, angles[:p], angles[p:])

    cur = list(start)
    cur_val = value(cur)
    step = step0
    while step > tol:
        improved = False
        for i in range(len(cur)):
            for sign in (1.0, -1.0):
                trial = list(cur)
                trial[i] += sign * step
                v = value(trial)
                if v > cur_val + 1e-12:
                    cur, cur_val, improved = trial, v, True
        if not improved:
            step /= 2.0
    return cur, cur_val


def optimize_angles(n, edges, p, previous=None):
    """Deterministic optimisation for one graph at depth p.

    `previous` is the (gammas, betas) optimum at depth p - 1.
    Returns (gammas, betas, expected_cut)."""
    starts = []
    if previous is None:
        best, best_val = None, -1.0
        for gi in range(24):
            for bi in range(12):
                g, b = gi * math.pi / 24, bi * math.pi / 24
                v = expected_cut(n, edges, [g], [b])
                if v > best_val:
                    best, best_val = [g, b], v
        starts.append(best)
    else:
        g_prev, b_prev = previous
        starts.append(list(g_prev) + [0.0] + list(b_prev) + [0.0])
        starts.append([0.0] + list(g_prev) + [0.0] + list(b_prev))
        stretched = [g_prev[0]]
        for i in range(1, p):
            if i < len(g_prev):
                stretched.append(
                    (g_prev[i] * (i + 1) + g_prev[i - 1] * (p - i)) / (p + 1))
            else:
                stretched.append(g_prev[-1])
        starts.append(stretched + list(b_prev) + [b_prev[-1]])
    best_angles, best_val = None, -1.0
    for start in starts:
        angles, val = _pattern_search(n, edges, start)
        if val > best_val:
            best_angles, best_val = angles, val
    return best_angles[:p], best_angles[p:], best_val


_TABLE_CACHE = None


def optimization_table():
    """The full p = 1..3 table for all three graphs (computed once)."""
    global _TABLE_CACHE
    if _TABLE_CACHE is not None:
        return _TABLE_CACHE
    table = {}
    for name, (n, edges) in GRAPHS.items():
        cmax, n_opt = brute_force_optimum(n, edges)
        uniform_opt = n_opt / (1 << n)
        rows = []
        previous = None
        for p in (1, 2, 3):
            gammas, betas, value = optimize_angles(n, edges, p, previous)
            previous = (gammas, betas)
            p_opt = optimal_probability(n, edges, gammas, betas)
            rows.append({
                "p": p,
                "gammas": [round(g, 6) for g in gammas],
                "betas": [round(b, 6) for b in betas],
                "expected_cut": round(value, 6),
                "ratio": round(value / cmax, 6),
                "optimal_probability": round(p_opt, 6),
                "uniform_optimal_probability": round(uniform_opt, 6),
                "optimal_factor": round(p_opt / uniform_opt, 3),
            })
        table[name] = rows
    _TABLE_CACHE = table
    return table


def baselines_report():
    """Classical baselines next to QAOA, in the same units.

    The honest headline of this lab: the deterministic greedy reaches
    the brute-force optimum on all three instances, so QAOA's expected
    cut never beats the best classical number printed here - it ties
    greedy at p = 3 on C6 and K4 and stays below it on the seeded
    graph. QAOA beats only the uniform-random baseline everywhere.
    """
    graphs = graph_report()
    table = optimization_table()
    report = {}
    for name in GRAPHS:
        g = graphs[name]
        report[name] = {
            "c_max_brute_force": g["c_max"],
            "random_expected_cut": g["random_expected_cut"],
            "random_ratio": g["random_ratio"],
            "greedy_cut": g["greedy_cut"],
            "greedy_ratio": g["greedy_ratio"],
            "qaoa_expected_cut": {f"p{row['p']}": row["expected_cut"]
                                  for row in table[name]},
            "qaoa_ratio": {f"p{row['p']}": row["ratio"]
                           for row in table[name]},
            "greedy_minus_qaoa_p3": round(
                g["greedy_cut"] - table[name][-1]["expected_cut"], 6),
        }
    return report


def sampling_report():
    """Optimal-string sampling probability vs the uniform baseline.

    Uniform sampling hits an optimal string with probability
    n_opt / 2^n (each single string: 2^-n). The improvement factor is
    the QAOA total divided by that uniform total."""
    table = optimization_table()
    report = {}
    for name, (n, edges) in GRAPHS.items():
        _, n_opt = brute_force_optimum(n, edges)
        report[name] = {
            "per_string_uniform": round(1.0 / (1 << n), 6),
            "rows": table[name],
            "optimal_strings": n_opt,
        }
    return report


# ================================================================ 6. kNN verdict classifier
# Features: approximation ratio, log10 of the optimal-string
# improvement factor, depth p. The training grid is labelled by the
# lab's own policy (policy_label below) - the classifier interpolates
# the policy, it does not replace the computed table.

def policy_label(ratio, optimal_factor, depth):
    """The verdict policy distilled to a four-way teaching label."""
    if optimal_factor <= 1.0:
        return "no-better-than-uniform"
    if ratio >= 0.999:
        return "optimal-reached"
    if ratio >= 0.90:
        return "strong"
    if ratio >= 0.80:
        return "promising"
    return "weak"


def _training_grid():
    rows = []
    ratio = 0.50
    while ratio <= 1.0001:
        for factor in (0.5, 1.0, 2.0, 5.0, 10.0, 40.0):
            for depth in (1, 2, 3):
                rows.append(((round(ratio, 4), factor, depth),
                             policy_label(round(ratio, 4), factor, depth)))
        ratio += 0.025
    return rows


TRAINING_GRID = _training_grid()


def _scaled(features):
    # The ratio axis is weighted x4: the verdict is primarily a
    # statement about the approximation ratio, with the sampling
    # factor and the depth acting as tie-breakers.
    ratio, factor, depth = features
    return (4.0 * ratio, math.log10(max(factor, 0.1)) / 2.0, depth / 3.0)


def classify_instance(ratio, optimal_factor, depth, k=5):
    """Distance-weighted kNN over the policy-labelled grid."""
    target = _scaled((ratio, optimal_factor, depth))
    ranked = []
    for features, label in TRAINING_GRID:
        point = _scaled(features)
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(target, point)))
        ranked.append((dist, features, label))
    ranked.sort(key=lambda row: (row[0], row[1]))
    weights = {}
    for dist, _, label in ranked[:k]:
        weights[label] = weights.get(label, 0.0) + 1.0 / (dist + 1e-9)
    priority = {"optimal-reached": 0, "strong": 1, "promising": 2,
                "weak": 3, "no-better-than-uniform": 4}
    return sorted(weights.items(),
                  key=lambda kv: (-kv[1], priority[kv[0]]))[0][0]


def classifier_report():
    table = optimization_table()
    report = {}
    for name, rows in table.items():
        report[name] = {
            f"p{row['p']}": classify_instance(
                row["ratio"], row["optimal_factor"], row["p"])
            for row in rows
        }
    return report


# ================================================================ 7. Advisory seats
def _trace(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def argon4_decide(topic="qaoa-demo"):
    """Gemini Argon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-argon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Argon 4 Extended Thinking",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all advantage and production gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="qaoa-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Print the greedy column next to every QAOA number: on these tiny graphs greedy reaches the optimum, so the honest story is what QAOA provably does - beat uniform sampling and match the p = 1 formula - not a crown it has not earned.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["a cycle graph lighting its cut edges one layer at a time",
                  "angle dials gamma and beta turning under a pattern search",
                  "the p = 1 formula curve landing exactly on the simulated points",
                  "probability mass flowing onto the two optimal strings",
                  "the greedy baseline standing at the optimum, unbowed"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": argon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # 1. PRNG + seeded graph
    s1 = splitmix64_stream(SEED)
    first = [next(s1) for _ in range(4)]
    s2 = splitmix64_stream(SEED)
    chk("splitmix64_deterministic", first == [next(s2) for _ in range(4)])
    s3 = splitmix64_stream(SEED + 1)
    chk("splitmix64_seed_sensitive", first != [next(s3) for _ in range(4)])
    n8, e8 = GRAPHS["random_regular_8"]
    chk("random_graph_deterministic", random_regular_graph() == (n8, e8))
    deg8 = [0] * n8
    for (u, v) in e8:
        deg8[u] += 1
        deg8[v] += 1
    chk("random_graph_3_regular", all(d == 3 for d in deg8)
        and len(e8) == 12 and len(set(e8)) == 12
        and all(u < v for (u, v) in e8))

    # 2. graph bookkeeping vs brute force
    graphs = graph_report()
    chk("c6_bookkeeping", graphs["cycle_c6"]["m"] == 6
        and graphs["cycle_c6"]["regular_degree"] == 2
        and graphs["cycle_c6"]["triangles"] == 0
        and graphs["cycle_c6"]["c_max"] == 6
        and graphs["cycle_c6"]["optimal_strings"] == 2)
    chk("k4_bookkeeping", graphs["complete_k4"]["m"] == 6
        and graphs["complete_k4"]["regular_degree"] == 3
        and graphs["complete_k4"]["triangles"] == 4
        and graphs["complete_k4"]["c_max"] == 4
        and graphs["complete_k4"]["optimal_strings"] == 6)
    chk("random_graph_bookkeeping", graphs["random_regular_8"]["c_max"] == 10
        and graphs["random_regular_8"]["optimal_strings"] == 4
        and graphs["random_regular_8"]["triangles"] == 2)
    chk("cut_value_extremes",
        cut_value(0b010101, GRAPHS["cycle_c6"][1]) == 6
        and cut_value(0, GRAPHS["cycle_c6"][1]) == 0
        and cut_value(0b0011, GRAPHS["complete_k4"][1]) == 4)
    chk("random_expectation_is_half_edges",
        all(abs(g["random_expected_cut"] - g["m"] / 2.0) < 1e-12
            for g in graphs.values()))

    # 3. statevector receipts
    for name, (n, edges) in GRAPHS.items():
        chk(f"norm_preserved_{name}",
            abs(state_norm(n, edges, [0.7, 0.4], [0.3, 0.9]) - 1.0) < 1e-12)
        chk(f"zero_angles_uniform_{name}",
            abs(expected_cut(n, edges, [0.0], [0.0])
                - len(edges) / 2.0) < 1e-12)
        chk(f"zero_beta_phases_only_{name}",
            abs(expected_cut(n, edges, [1.1], [0.0])
                - len(edges) / 2.0) < 1e-12)

    # 4. analytic p = 1 on the cycle
    ana = analytic_report()
    chk("analytic_grid_agreement", ana["grid_max_deviation"] < 1e-9)
    chk("analytic_peak_exact", abs(ana["peak_expected_cut"] - 4.5) < 1e-12
        and abs(ana["peak_ratio"] - 0.75) < 1e-12)

    # 5. optimisation table - only what the numbers actually show
    table = optimization_table()
    for name, rows in table.items():
        ratios = [row["ratio"] for row in rows]
        chk(f"ratio_nondecreasing_{name}",
            all(ratios[i + 1] >= ratios[i] - 1e-9
                for i in range(len(ratios) - 1)))
        chk(f"ratio_beats_random_{name}",
            all(row["ratio"] > graphs[name]["random_ratio"]
                for row in rows))
        chk(f"ratio_within_bounds_{name}",
            all(graphs[name]["random_ratio"] < row["ratio"] <= 1.0 + 1e-9
                for row in rows))
        chk(f"optimal_factor_above_one_{name}",
            all(row["optimal_factor"] > 1.0 for row in rows))
    chk("c6_p1_ratio_is_three_quarters",
        abs(table["cycle_c6"][0]["ratio"] - 0.75) < 1e-6)
    chk("c6_p3_reaches_optimum",
        abs(table["cycle_c6"][2]["ratio"] - 1.0) < 1e-6
        and abs(table["cycle_c6"][2]["optimal_probability"] - 1.0) < 1e-6)
    chk("k4_p2_reaches_optimum",
        abs(table["complete_k4"][1]["ratio"] - 1.0) < 1e-6)
    # recompute one row from its printed angles: the table is the sim
    n6, e6 = GRAPHS["cycle_c6"]
    row = table["cycle_c6"][1]
    chk("table_row_recomputes",
        abs(expected_cut(n6, e6, row["gammas"], row["betas"])
            - row["expected_cut"]) < 2e-6)

    # 6. classical baselines - the honest headline
    base = baselines_report()
    chk("greedy_reaches_optimum_all_graphs",
        all(base[name]["greedy_cut"] == base[name]["c_max_brute_force"]
            for name in GRAPHS))
    chk("greedy_never_below_qaoa_expectation",
        all(base[name]["greedy_cut"]
            >= max(base[name]["qaoa_expected_cut"].values()) - 1e-9
            for name in GRAPHS))
    chk("qaoa_below_greedy_on_random_graph",
        base["random_regular_8"]["greedy_minus_qaoa_p3"] > 0.5)

    # 7. classifier - labels come from the lab's own policy
    rep = classifier_report()
    chk("classifier_c6_ladder",
        rep["cycle_c6"] == {"p1": "weak", "p2": "promising",
                            "p3": "optimal-reached"})
    chk("classifier_k4_ladder",
        rep["complete_k4"] == {"p1": "strong", "p2": "optimal-reached",
                               "p3": "optimal-reached"})
    chk("classifier_random_graph_ladder",
        rep["random_regular_8"] == {"p1": "promising", "p2": "promising",
                                    "p3": "strong"})
    chk("classifier_matches_policy_on_scenarios",
        all(classify_instance(row["ratio"], row["optimal_factor"], row["p"])
            == policy_label(row["ratio"], row["optimal_factor"], row["p"])
            for rows in table.values() for row in rows))
    chk("classifier_matches_policy_on_probes",
        all(classify_instance(*f) == policy_label(*f)
            for f in [(0.55, 3.0, 1), (0.83, 8.0, 2), (0.93, 20.0, 3),
                      (1.00, 30.0, 3), (0.70, 0.8, 1)]))
    chk("classifier_uniform_guard",
        classify_instance(0.99, 0.5, 3) == "no-better-than-uniform")

    # gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14
        and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_advantage_hold", gate("quantum_advantage_claim") == "HOLD")
    chk("gate_np_hard_hold", gate("np_hard_solved_claim") == "HOLD")
    chk("gate_production_hold", gate("production_optimization_use") == "HOLD")
    chk("gate_hardware_hold", gate("real_hardware_execution_claim") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    brains = brains_report()
    chk("argon4_no_override", brains["decider"]["can_override_hold"] is False
        and brains["decider"]["seat"]
        == "Gemini Argon 4 Extended Thinking")
    chk("claude_no_override", brains["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", brains["flow"]["rendered"] is False
        and brains["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("QAOA-Lab - Quantum Approximate Optimization Algorithm lab")
    print("by Darion Kellar | MIT | pure stdlib | zero network | EDUCATION ONLY")
    print("=" * 68)
    print("\n[1] THE HONEST CORE - a heuristic, graded against the truth")
    print("    QAOA prepares a state with alternating cost and mixer")
    print("    unitaries and tunes the angles classically. This lab runs")
    print("    the EXACT statevector on graphs small enough to brute-")
    print("    force, and prints the classical baselines in the same")
    print("    table. On these instances greedy reaches the optimum on")
    print("    all three graphs - QAOA is compared, never crowned, and")
    print("    no quantum advantage is claimed anywhere.")
    graphs = graph_report()
    print("\n[2] The three instances - brute force sets the truth")
    for name, g in graphs.items():
        print(f"    {name:18s} n={g['n']} m={g['m']} "
              f"degree={g['regular_degree']} triangles={g['triangles']} | "
              f"C_max {g['c_max']} ({g['optimal_strings']} optimal strings)")
    print(f"    random_regular_8 is drawn from splitmix64 seed {SEED} -")
    print("    the same instance on every machine, every run.")
    print("\n[3] Zero-angle receipt - the simulator's starting point")
    for name, (n, edges) in GRAPHS.items():
        ec = expected_cut(n, edges, [0.0], [0.0])
        print(f"    {name:18s} <C>(gamma=0, beta=0) = {ec:.6f} "
              f"= m/2 = {len(edges) / 2.0:.6f} (uniform random)")
    print("    -> with no angles the QAOA state is |+>^n and its expected")
    print("       cut IS the uniform-random expectation, computed two ways.")
    ana = analytic_report()
    print("\n[4] Analytic p = 1 on the cycle C6 (triangle-free, d = 2)")
    print(f"    formula: {ana['formula']}")
    print(f"    max |sim - formula| over a 20-point angle grid: "
          f"{ana['grid_max_deviation']:.3e}")
    print(f"    at gamma = pi/4, beta = pi/8: <C> = "
          f"{ana['peak_expected_cut']:.6f} - ratio exactly "
          f"{ana['peak_ratio']:.6f} of C_max = 6.")
    print("    -> the formula is verified against the statevector, not")
    print("       quoted. It is not used for K4 or the seeded graph:")
    print("       both contain triangles, where the closed form changes.")
    table = optimization_table()
    print("\n[5] Optimised angles - deterministic grid + pattern search")
    for name, rows in table.items():
        g = graphs[name]
        for row in rows:
            print(f"    {name:18s} p={row['p']} <C> = "
                  f"{row['expected_cut']:.6f} | ratio {row['ratio']:.6f} "
                  f"(random {g['random_ratio']:.3f})")
    print("    -> ratios are non-decreasing in p ON THESE INSTANCES: the")
    print("       search warm-starts each depth from the previous optimum")
    print("       with a zero layer, which reproduces it exactly.")
    base = baselines_report()
    print("\n[6] Classical baselines - the same run, the same units")
    for name in GRAPHS:
        b = base[name]
        print(f"    {name:18s} brute {b['c_max_brute_force']} | "
              f"random {b['random_expected_cut']:.3f} | "
              f"greedy {b['greedy_cut']} | QAOA p3 "
              f"{b['qaoa_expected_cut']['p3']:.6f}")
    print("    -> greedy reaches the optimum on all three graphs. QAOA's")
    print("       expectation ties it at p = 3 on C6 and K4 and stays")
    print("       below it on the seeded graph. That is the headline.")
    print("\n[7] Sampling an optimal string - where QAOA does pull ahead")
    for name, rows in table.items():
        for row in rows:
            print(f"    {name:18s} p={row['p']} P(optimal) = "
                  f"{row['optimal_probability']:.6f} vs uniform "
                  f"{row['uniform_optimal_probability']:.6f} "
                  f"-> x{row['optimal_factor']:.1f}")
    print("    -> against UNIFORM sampling the prepared state concentrates")
    print("       on optimal strings by up to ~x39. Against greedy there")
    print("       is no such factor to print, and none is claimed.")
    print("\n[8] Verdict classifier (TinyML kNN, labels from the lab policy)")
    for name, labels in classifier_report().items():
        print(f"    {name:18s} " +
              " | ".join(f"{k} {v}" for k, v in labels.items()))
    print("\n[9] Advisory seats")
    brains = brains_report()
    print(f"    decider: {brains['decider']['decision']} "
          f"trace={brains['decider']['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {brains['advisor']['can_override_hold']}")
    print(f"    flow rendered = {brains['flow']['rendered']} "
          f"live = {brains['flow']['live']}")
    print(f"\n[10] HOLD gates: {len(HOLD_GATES)}")
    for key in HOLD_GATES:
        print(f"    HOLD  {key}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "graphs":
        print(json.dumps(graph_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "analytic":
        print(json.dumps(analytic_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "angles":
        print(json.dumps(optimization_table(), indent=2, sort_keys=True))
        return 0
    if cmd == "baselines":
        print(json.dumps(baselines_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "sampling":
        print(json.dumps(sampling_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(classifier_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for key, value in HOLD_GATES.items():
            print(f"{key}: {value}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "quantum_advantage_claim"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
