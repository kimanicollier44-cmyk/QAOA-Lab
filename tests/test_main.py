"""Tests for QAOA-Lab. Every test grades a computed number against a
closed form, a brute-force truth, or an independent implementation
in main.py - including the honest headline that greedy wins."""
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main as q

TOL = 1e-9


def test_splitmix64_deterministic():
    a = q.splitmix64_stream(q.SEED)
    b = q.splitmix64_stream(q.SEED)
    assert [next(a) for _ in range(8)] == [next(b) for _ in range(8)]


def test_random_graph_rebuilds_identically():
    assert q.random_regular_graph() == q.GRAPHS["random_regular_8"]


def test_random_graph_is_3_regular():
    n, edges = q.GRAPHS["random_regular_8"]
    degrees = [0] * n
    for (u, v) in edges:
        degrees[u] += 1
        degrees[v] += 1
    assert all(d == 3 for d in degrees)
    assert len(edges) == 12 and len(set(edges)) == 12


def test_brute_force_truths():
    assert q.brute_force_optimum(*q.GRAPHS["cycle_c6"]) == (6, 2)
    assert q.brute_force_optimum(*q.GRAPHS["complete_k4"]) == (4, 6)
    assert q.brute_force_optimum(*q.GRAPHS["random_regular_8"]) == (10, 4)


def test_cut_value_known_strings():
    _, c6 = q.GRAPHS["cycle_c6"]
    _, k4 = q.GRAPHS["complete_k4"]
    assert q.cut_value(0b010101, c6) == 6
    assert q.cut_value(0b000000, c6) == 0
    assert q.cut_value(0b0011, k4) == 4


def test_random_expectation_is_m_over_2():
    for _, edges in q.GRAPHS.values():
        assert q.random_expected_cut(edges) == len(edges) / 2.0


def test_zero_angles_give_uniform_expectation():
    for n, edges in q.GRAPHS.values():
        ec = q.expected_cut(n, edges, [0.0], [0.0])
        assert abs(ec - len(edges) / 2.0) < TOL


def test_zero_beta_phases_do_not_change_expectation():
    for n, edges in q.GRAPHS.values():
        ec = q.expected_cut(n, edges, [1.1], [0.0])
        assert abs(ec - len(edges) / 2.0) < TOL


def test_state_norm_preserved():
    for n, edges in q.GRAPHS.values():
        assert abs(q.state_norm(n, edges, [0.7, 0.4], [0.3, 0.9]) - 1.0) < 1e-12


def test_analytic_formula_matches_simulator_on_grid():
    n, edges = q.GRAPHS["cycle_c6"]
    for gamma in (0.1, 0.3, 0.7, 1.0, 1.3):
        for beta in (0.05, 0.2, 0.39, 0.6):
            sim = q.expected_cut(n, edges, [gamma], [beta])
            ana = q.analytic_p1_expectation(6, 2, gamma, beta)
            assert abs(sim - ana) < TOL


def test_analytic_peak_is_three_quarters():
    n, edges = q.GRAPHS["cycle_c6"]
    ec = q.expected_cut(n, edges, [math.pi / 4], [math.pi / 8])
    assert abs(ec - 4.5) < 1e-12
    assert abs(ec / 6.0 - 0.75) < 1e-12


def test_table_ratios_nondecreasing_in_p():
    graphs = q.graph_report()
    for name, rows in q.optimization_table().items():
        ratios = [r["ratio"] for r in rows]
        assert all(b >= a - TOL for a, b in zip(ratios, ratios[1:]))
        assert all(r > graphs[name]["random_ratio"] for r in ratios)


def test_table_c6_p1_ratio():
    row = q.optimization_table()["cycle_c6"][0]
    assert abs(row["ratio"] - 0.75) < 1e-6


def test_table_row_recomputes_from_printed_angles():
    n, edges = q.GRAPHS["random_regular_8"]
    row = q.optimization_table()["random_regular_8"][2]
    ec = q.expected_cut(n, edges, row["gammas"], row["betas"])
    assert abs(ec - row["expected_cut"]) < 2e-6


def test_optimal_probability_factors_above_one():
    for rows in q.optimization_table().values():
        for row in rows:
            assert row["optimal_factor"] > 1.0
            assert 0.0 < row["optimal_probability"] <= 1.0


def test_c6_p3_sampling_is_certain():
    row = q.optimization_table()["cycle_c6"][2]
    assert abs(row["optimal_probability"] - 1.0) < 1e-6
    assert abs(row["optimal_factor"] - 32.0) < 0.01


def test_greedy_reaches_brute_force_optimum():
    for name, (n, edges) in q.GRAPHS.items():
        cmax, _ = q.brute_force_optimum(n, edges)
        assert q.greedy_cut(n, edges) == cmax, name


def test_greedy_never_below_qaoa_expectation():
    base = q.baselines_report()
    for name in q.GRAPHS:
        assert base[name]["greedy_cut"] >= max(
            base[name]["qaoa_expected_cut"].values()) - TOL


def test_qaoa_stays_below_greedy_on_random_graph():
    base = q.baselines_report()["random_regular_8"]
    assert base["greedy_minus_qaoa_p3"] > 0.5


def test_classifier_ladders():
    rep = q.classifier_report()
    assert rep["cycle_c6"] == {"p1": "weak", "p2": "promising",
                               "p3": "optimal-reached"}
    assert rep["complete_k4"]["p1"] == "strong"
    assert rep["random_regular_8"]["p3"] == "strong"


def test_classifier_matches_policy_on_scenarios():
    for rows in q.optimization_table().values():
        for row in rows:
            f = (row["ratio"], row["optimal_factor"], row["p"])
            assert q.classify_instance(*f) == q.policy_label(*f)


def test_classifier_uniform_guard():
    assert q.classify_instance(0.99, 0.5, 3) == "no-better-than-uniform"
    assert q.policy_label(0.99, 0.5, 3) == "no-better-than-uniform"


def test_hold_gates():
    assert len(q.HOLD_GATES) == 14
    assert q.gate("quantum_advantage_claim") == "HOLD"
    assert q.gate("np_hard_solved_claim") == "HOLD"
    assert q.gate("production_optimization_use") == "HOLD"
    assert q.gate("run_simulation") == "PROCEED"


def test_brains_no_override():
    brains = q.brains_report()
    assert brains["decider"]["can_override_hold"] is False
    assert brains["decider"]["seat"] == "Gemini Argon 4 Extended Thinking"
    assert brains["advisor"]["can_override_hold"] is False
    assert brains["flow"]["rendered"] is False
    assert brains["flow"]["live"] == 0


def test_checks_all_pass():
    checks = q.run_checks()
    assert all(ok for _, ok in checks), [n for n, ok in checks if not ok]


def test_hold_demo_exits_2():
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"),
         "hold-demo"],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "quantum_advantage_claim" in proc.stdout
