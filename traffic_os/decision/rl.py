"""Optional RL signal control — a single-junction DQN (PyTorch, CPU).

This is an *optional advanced mode* alongside the explainable max-pressure engine
(which remains the default). It demonstrates that a learned policy can beat a naive
fixed-timer on a toy junction with asymmetric demand. Multi-agent / city-scale RL
remains roadmap (hard to validate); the max-pressure engine is the production path.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from traffic_os.common.logging import get_logger

log = get_logger("decision.rl")


class JunctionEnv:
    """Minimal 2-phase signalised junction with asymmetric Poisson arrivals."""

    def __init__(
        self,
        arrival_rates=(1.6, 0.5),
        capacity: float = 2.0,
        max_queue: float = 60.0,
        horizon: int = 40,
        seed: int = 0,
    ) -> None:
        self.arrival_rates = arrival_rates
        self.capacity = capacity
        self.max_queue = max_queue
        self.horizon = horizon
        self.rng = random.Random(seed)
        self.n_actions = len(arrival_rates)
        self.queues = [0.0, 0.0]
        self.t = 0

    def reset(self) -> list[float]:
        self.queues = [0.0, 0.0]
        self.t = 0
        return self._state()

    def _state(self) -> list[float]:
        return [min(q / self.max_queue, 1.0) for q in self.queues]

    def step(self, action: int):
        # arrivals
        for i, rate in enumerate(self.arrival_rates):
            self.queues[i] = min(self.max_queue, self.queues[i] + self._poisson(rate))
        # serve the green phase
        served = min(self.queues[action], self.capacity)
        self.queues[action] -= served
        reward = -sum(self.queues)  # minimise total waiting
        self.t += 1
        done = self.t >= self.horizon
        return self._state(), reward, done

    def _poisson(self, lam: float) -> int:
        import math

        ll, k, p = math.exp(-lam), 0, 1.0
        while True:
            k += 1
            p *= self.rng.random()
            if p <= ll:
                return k - 1


@dataclass
class RLResult:
    dqn_avg_queue: float
    fixed_avg_queue: float
    greedy_avg_queue: float
    improvement_vs_fixed_pct: float
    episodes: int


def _avg_queue(env: JunctionEnv, policy, episodes: int = 20) -> float:
    total = 0.0
    steps = 0
    for ep in range(episodes):
        env.rng.seed(1000 + ep)
        s = env.reset()
        done = False
        while not done:
            a = policy(s)
            s, _r, done = env.step(a)
            total += sum(env.queues)
            steps += 1
    return total / max(steps, 1)


def train_and_evaluate(*, episodes: int = 120, eval_episodes: int = 20, seed: int = 0) -> RLResult:
    import numpy as np
    import torch
    import torch.nn as nn

    torch.manual_seed(seed)
    env = JunctionEnv(seed=seed)
    n_state, n_act = 2, env.n_actions

    net = nn.Sequential(
        nn.Linear(n_state, 32), nn.ReLU(), nn.Linear(32, 32), nn.ReLU(), nn.Linear(32, n_act)
    )
    target = nn.Sequential(
        nn.Linear(n_state, 32), nn.ReLU(), nn.Linear(32, 32), nn.ReLU(), nn.Linear(32, n_act)
    )
    target.load_state_dict(net.state_dict())
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    buffer: deque = deque(maxlen=5000)
    gamma, batch = 0.95, 64
    eps, eps_min, eps_decay = 1.0, 0.05, 0.97

    def act(state, epsilon):
        if random.random() < epsilon:
            return random.randrange(n_act)
        with torch.no_grad():
            q = net(torch.tensor(state, dtype=torch.float32))
        return int(torch.argmax(q).item())

    for ep in range(episodes):
        env.rng.seed(ep)
        s = env.reset()
        done = False
        while not done:
            a = act(s, eps)
            s2, r, done = env.step(a)
            buffer.append((s, a, r, s2, done))
            s = s2
            if len(buffer) >= batch:
                sample = random.sample(buffer, batch)
                bs = torch.tensor([x[0] for x in sample], dtype=torch.float32)
                ba = torch.tensor([x[1] for x in sample], dtype=torch.int64).unsqueeze(1)
                br = torch.tensor([x[2] for x in sample], dtype=torch.float32).unsqueeze(1)
                bs2 = torch.tensor([x[3] for x in sample], dtype=torch.float32)
                bd = torch.tensor([x[4] for x in sample], dtype=torch.float32).unsqueeze(1)
                q = net(bs).gather(1, ba)
                with torch.no_grad():
                    qn = target(bs2).max(1, keepdim=True)[0]
                    tgt = br + gamma * qn * (1 - bd)
                loss = nn.functional.smooth_l1_loss(q, tgt)
                opt.zero_grad()
                loss.backward()
                opt.step()
        eps = max(eps_min, eps * eps_decay)
        if ep % 10 == 0:
            target.load_state_dict(net.state_dict())

    dqn_policy = lambda s: act(s, 0.0)  # noqa: E731
    fixed_policy = _make_fixed_policy()
    greedy_policy = lambda s: int(np.argmax(s))  # noqa: E731

    dqn_q = _avg_queue(env, dqn_policy, eval_episodes)
    fixed_q = _avg_queue(env, fixed_policy, eval_episodes)
    greedy_q = _avg_queue(env, greedy_policy, eval_episodes)
    impr = (fixed_q - dqn_q) / fixed_q * 100.0 if fixed_q else 0.0
    res = RLResult(round(dqn_q, 2), round(fixed_q, 2), round(greedy_q, 2), round(impr, 1), episodes)
    log.info("RL eval: %s", res)
    return res


def _make_fixed_policy():
    state = {"t": 0}

    def policy(_s):
        state["t"] += 1
        return state["t"] % 2

    return policy
