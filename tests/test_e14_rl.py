"""E14: optional RL signal control (single-junction DQN)."""

from __future__ import annotations

import pytest

pytest.importorskip("torch")

from traffic_os.decision.rl import JunctionEnv, train_and_evaluate  # noqa: E402


def test_env_dynamics():
    env = JunctionEnv(arrival_rates=(2.0, 0.1), capacity=2.0, horizon=10, seed=1)
    s = env.reset()
    assert s == [0.0, 0.0]
    # serving phase 0 repeatedly keeps phase-0 queue bounded; phase-1 barely grows
    done = False
    steps = 0
    while not done:
        s, r, done = env.step(0)
        steps += 1
        assert r <= 0  # reward is negative total queue
    assert steps == 10


def test_max_pressure_beats_fixed_and_dqn_competitive():
    res = train_and_evaluate(episodes=120, eval_episodes=20, seed=0)
    # max-pressure (greedy) clearly beats the naive fixed timer — the production path
    assert res.greedy_avg_queue < res.fixed_avg_queue
    # the learned DQN policy is at least competitive with the fixed timer
    assert res.dqn_avg_queue < res.fixed_avg_queue * 1.10
