"""Daily battery dispatch optimisation against day ahead prices.

One delivery day at a time, start and end empty, so every schedule is one
that could be submitted in a single day ahead auction. Solved as a linear
programme with HiGHS; if the linear solution charges and discharges in the
same interval (possible only when prices are negative) the day is solved
again as a mixed integer programme that forbids it.
"""
from functools import lru_cache

import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

DT = 0.25  # hours per interval


@lru_cache(maxsize=None)
def _matrices(n: int, eta_c: float, eta_d: float):
    eye = sparse.identity(n, format="csr")
    sub = sparse.diags([np.ones(n - 1)], [-1], shape=(n, n), format="csr")
    # state of charge balance: s_t - s_{t-1} - eta_c*dt*c_t + dt/eta_d*d_t = 0
    a_eq = sparse.hstack([-eta_c * DT * eye, (DT / eta_d) * eye, eye - sub], format="csr")
    return a_eq


def solve_day(prices: np.ndarray, power: float, hours: float, rte: float,
              cycles: float):
    """Return (revenue_eur, charge_mw, discharge_mw) for one day.

    prices  : EUR/MWh per quarter hour
    power   : MW (charge and discharge limit)
    hours   : storage duration, energy capacity = power * hours (MWh)
    rte     : round trip efficiency (split equally between charge and discharge)
    cycles  : cap on full equivalent cycles per day
    """
    n = len(prices)
    eta = float(np.sqrt(rte))
    energy = power * hours
    a_eq = _matrices(n, eta, eta)
    cost = np.concatenate([prices * DT, -prices * DT, np.zeros(n)])
    # throughput cap measured on the state of charge side
    a_ub = sparse.csr_matrix(
        np.concatenate([np.zeros(n), np.full(n, DT / eta), np.zeros(n)])[None, :])
    lb = np.zeros(3 * n)
    ub = np.concatenate([np.full(2 * n, power), np.full(n, energy)])
    ub[-1] = 0.0  # end the day empty
    res = linprog(cost, A_ub=a_ub, b_ub=[cycles * energy], A_eq=a_eq,
                  b_eq=np.zeros(n), bounds=np.column_stack([lb, ub]), method="highs")
    assert res.status == 0, res.message
    c, d = res.x[:n], res.x[n:2 * n]
    if np.any((c > 1e-7) & (d > 1e-7)):
        # forbid simultaneous charge and discharge with one binary per interval
        eye = sparse.identity(n, format="csr")
        zero = sparse.csr_matrix((n, n))
        a_eq_m = sparse.hstack([a_eq, zero], format="csr")
        a_ub_m = sparse.hstack([a_ub, sparse.csr_matrix((1, n))], format="csr")
        a_c = sparse.hstack([eye, zero, zero, -power * eye], format="csr")  # c <= P u
        a_d = sparse.hstack([zero, eye, zero, power * eye], format="csr")   # d <= P (1-u)
        cons = [LinearConstraint(a_eq_m, 0, 0),
                LinearConstraint(a_ub_m, -np.inf, cycles * energy),
                LinearConstraint(a_c, -np.inf, 0),
                LinearConstraint(a_d, -np.inf, power)]
        integrality = np.concatenate([np.zeros(3 * n), np.ones(n)])
        res = milp(np.concatenate([cost, np.zeros(n)]), constraints=cons,
                   integrality=integrality,
                   bounds=Bounds(np.concatenate([lb, np.zeros(n)]),
                                 np.concatenate([ub, np.ones(n)])),
                   options={"mip_rel_gap": 1e-9})
        assert res.status == 0, res.message
        c, d = res.x[:n], res.x[n:2 * n]
    c = np.where(c < 1e-9, 0.0, c)
    d = np.where(d < 1e-9, 0.0, d)
    revenue = float(np.sum(prices * (d - c)) * DT)
    return revenue, c, d


def settle(prices: np.ndarray, c: np.ndarray, d: np.ndarray) -> float:
    """Revenue of a fixed schedule at realised prices."""
    return float(np.sum(prices * (d - c)) * DT)
