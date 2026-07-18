"""
Rock Mass Variability Analysis — Streamlit Edition (v2.0)
===========================================================
Monte Carlo Simulation | RMR | Q-System | Hoek-Brown | Mohr-Coulomb
Support Pressure | Tunnel CCM (simplified + Hoek-Brown) | Reliability | ANN
Correlated Sampling | Spatial Variability / Random Fields | Regression Tools
Construction Monitoring (Beta)

Run:
    pip install streamlit numpy pandas scipy openpyxl
    streamlit run rock_mass_variability_analysis.py

v2.0 additions implement the recommendations for further development:
    - Correlated input sampling (Iman-Conover rank correlation, Cholesky-based)
    - Spatial variability / 1-D random fields along the tunnel alignment
      (Vanmarcke 1977 variance reduction; methodology per Wang & Cao 2014)
    - Extended CCM using the Hoek-Brown based closed-form curves
      (Carranza-Torres & Fairhurst 1999; Duncan Fama 1993; Hoek 2000)
    - Linear & auto-regression tools for site-specific formulas
    - Construction Monitoring (Beta) — periodic-update prototype

Author: Converted from RockMassRiskAnalysis_v6.jsx; extended for v2.0
"""
APP_VERSION = "2.0.0"

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
import math
import io
import json
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Rock Mass Variability Analysis", page_icon="⛰️", layout="wide", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS & DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────
GAMMA_ROCK = 0.027  # MN/m³

PARAM_RANGES = {
    "RQD":          {"min": 0,    "max": 100,   "warnLo": 10,   "warnHi": 100, "unit": "%",     "ref": "Deere (1964)"},
    "Jn":           {"min": 0.5,  "max": 20,    "warnLo": 0.5,  "warnHi": 20,  "unit": "",      "ref": "Barton et al. (1974)"},
    "Jr":           {"min": 0.5,  "max": 4,     "warnLo": 0.5,  "warnHi": 4,   "unit": "",      "ref": "Barton et al. (1974)"},
    "Ja":           {"min": 0.75, "max": 20,    "warnLo": 0.75, "warnHi": 20,  "unit": "",      "ref": "Barton et al. (1974)"},
    "Jw":           {"min": 0.05, "max": 1,     "warnLo": 0.05, "warnHi": 1,   "unit": "",      "ref": "Barton et al. (1974)"},
    "SRF":          {"min": 0.5,  "max": 400,   "warnLo": 0.5,  "warnHi": 20,  "unit": "",      "ref": "Barton et al. (1974)"},
    "GSI":          {"min": 0,    "max": 100,   "warnLo": 5,    "warnHi": 100, "unit": "",      "ref": "Hoek & Brown (1997)"},
    "mi":           {"min": 0.5,  "max": 35,    "warnLo": 1,    "warnHi": 33,  "unit": "",      "ref": "Hoek et al. (1995)"},
    "UCS":          {"min": 0.25, "max": 250,   "warnLo": 1,    "warnHi": 250, "unit": "MPa",   "ref": "ISRM (1978)"},
    "D":            {"min": 0,    "max": 1,     "warnLo": 0,    "warnHi": 1,   "unit": "",      "ref": "Hoek et al. (2002)"},
    "MR":           {"min": 50,   "max": 1000,  "warnLo": 100,  "warnHi": 800, "unit": "",      "ref": "Deere (1968)"},
    "JointSpacing": {"min": 1,    "max": 10000, "warnLo": 6,    "warnHi": 6000,"unit": "mm",    "ref": "Bieniawski (1989)"},
    "JointCondition":{"min": 0,   "max": 30,    "warnLo": 0,    "warnHi": 30,  "unit": "0-30",  "ref": "Bieniawski (1989)"},
    "Groundwater":  {"min": 0,    "max": 15,    "warnLo": 0,    "warnHi": 15,  "unit": "0-15",  "ref": "Bieniawski (1989)"},
}

PARAM_GROUPS = [
    {
        "label": "Q-System Parameters",
        "params": [
            {"key": "RQD",  "label": "RQD",  "unit": "%",   "desc": "Rock Quality Designation (0–100)"},
            {"key": "Jn",   "label": "Jn",   "unit": "",    "desc": "Joint Set Number"},
            {"key": "Jr",   "label": "Jr",   "unit": "",    "desc": "Joint Roughness Number"},
            {"key": "Ja",   "label": "Ja",   "unit": "",    "desc": "Joint Alteration Number"},
            {"key": "Jw",   "label": "Jw",   "unit": "",    "desc": "Joint Water Reduction Factor"},
            {"key": "SRF",  "label": "SRF",  "unit": "",    "desc": "Stress Reduction Factor"},
        ],
    },
    {
        "label": "Hoek-Brown / GSI Parameters",
        "params": [
            {"key": "GSI",  "label": "GSI",  "unit": "",    "desc": "Geological Strength Index (0–100)"},
            {"key": "mi",   "label": "mi",   "unit": "",    "desc": "Hoek-Brown Intact Rock Constant"},
            {"key": "UCS",  "label": "UCS",  "unit": "MPa", "desc": "Uniaxial Compressive Strength"},
            {"key": "D",    "label": "D",    "unit": "",    "desc": "Disturbance Factor (0–1)"},
            {"key": "MR",   "label": "MR",   "unit": "",    "desc": "Modulus Ratio"},
        ],
    },
    {
        "label": "RMR Parameters",
        "params": [
            {"key": "JointSpacing",   "label": "Joint Spacing",          "unit": "mm",   "desc": "Average joint spacing"},
            {"key": "JointCondition", "label": "Joint Condition Rating",  "unit": "0-30", "desc": "Joint surface condition"},
            {"key": "Groundwater",    "label": "Groundwater Rating",      "unit": "0-15", "desc": "Groundwater condition"},
        ],
    },
]

ALL_PARAMS = [p for g in PARAM_GROUPS for p in g["params"]]
ALL_PARAM_KEYS = [p["key"] for p in ALL_PARAMS]

EM_MODES = {
    "HD": {
        "label": "Hoek-Diederichs (2006)",
        "formula": "Em = (UCS/100) × exp((GSI − 11D)/36) × 0.02",
        "deps": ["GSI", "UCS", "D"],
        "note": "Use when GSI, UCS and D are available",
    },
    "SP": {
        "label": "Serafim-Pereira (1983)",
        "formula": "Em = 10^((RMR − 10)/40)",
        "deps": ["UCS", "RQD", "JointSpacing", "JointCondition", "Groundwater"],
        "note": "Use when only RMR data is available",
    },
}

ALL_OUTPUTS = [
    # Core
    {"key": "Q",           "label": "Q-Value",                     "unit": "",       "group": "core"},
    {"key": "RMR",         "label": "RMR Score",                   "unit": "",       "group": "core"},
    {"key": "Em",          "label": "Deformation Modulus Em",       "unit": "GPa",    "group": "core"},
    {"key": "Ei",          "label": "Ei (Intact Rock)",             "unit": "GPa",    "group": "core"},
    {"key": "Rms",         "label": "Rock Mass Strength",           "unit": "MPa",    "group": "core"},
    {"key": "mb",          "label": "Hoek-Brown mb",                "unit": "",       "group": "core"},
    {"key": "s",           "label": "Hoek-Brown s",                 "unit": "",       "group": "core"},
    {"key": "a",           "label": "Hoek-Brown a",                 "unit": "",       "group": "core"},
    {"key": "cohesion",    "label": "Cohesion c'",                  "unit": "MPa",    "group": "core"},
    {"key": "friction",    "label": "Friction Angle φ'",            "unit": "°",      "group": "core"},
    # Support Pressure
    {"key": "Pv_terzaghi", "label": "Support Pressure (Terzaghi)", "unit": "MN/m²",  "group": "support"},
    {"key": "Pv_barton",   "label": "Support Pressure (Barton Q)", "unit": "MPa",    "group": "support"},
    {"key": "Pv_rmr",      "label": "Support Pressure (RMR)",      "unit": "MN/m²",  "group": "support"},
    # Tunnel Convergence
    {"key": "ui_kirsch",   "label": "Elastic Convergence ui",       "unit": "mm",     "group": "tunnel"},
    {"key": "rp_plastic",  "label": "Plastic Radius rp",            "unit": "m",      "group": "tunnel"},
    # Reliability
    {"key": "FS_dist",     "label": "Factor of Safety (FS)",        "unit": "",       "group": "reliability"},
]

OUTPUT_GROUPS = {
    "core":        "Core Rock Mass",
    "support":     "Support Pressure Estimation",
    "tunnel":      "Tunnel Convergence Analysis",
    "reliability": "Reliability / Factor of Safety",
}

OUTPUT_DEPS = {
    "Q":            ["RQD", "Jn", "Jr", "Ja", "Jw", "SRF"],
    "RMR":          ["UCS", "RQD", "JointSpacing", "JointCondition", "Groundwater"],
    "Em":           ["GSI", "UCS", "D", "RQD", "JointSpacing", "JointCondition", "Groundwater"],  # union
    "Ei":           ["MR", "UCS"],
    "Rms":          ["UCS", "GSI", "mi", "D"],
    "mb":           ["GSI", "mi", "UCS", "D"],
    "s":            ["GSI", "mi", "UCS", "D"],
    "a":            ["GSI", "mi", "UCS", "D"],
    "cohesion":     ["UCS", "GSI", "mi", "D"],
    "friction":     ["UCS", "GSI", "mi", "D"],
    "Pv_terzaghi":  ["UCS", "RQD", "JointSpacing", "JointCondition", "Groundwater"],
    "Pv_barton":    ["RQD", "Jn", "Jr", "Ja", "Jw", "SRF", "UCS"],
    "Pv_rmr":       ["UCS", "RQD", "JointSpacing", "JointCondition", "Groundwater"],
    "ui_kirsch":    ["UCS", "GSI", "mi", "D", "MR"],
    "rp_plastic":   ["UCS", "GSI", "mi", "D"],
    "FS_dist":      ["UCS", "GSI", "mi", "D"],
}

# Em-specific deps depending on mode
EM_DEPS = {
    "HD": ["GSI", "UCS", "D"],
    "SP": ["UCS", "RQD", "JointSpacing", "JointCondition", "Groundwater"],
}

DISTRIBUTIONS = ["Normal", "Lognormal", "Uniform", "Triangular", "Truncated Normal", "PERT", "Beta Scaled"]

DIST_FIELDS = {
    "Normal":         ["mean", "std"],
    "Lognormal":      ["mean", "std"],
    "Uniform":        ["min", "max"],
    "Triangular":     ["min", "mode", "max"],
    "Truncated Normal": ["mean", "std", "min", "max"],
    "PERT":           ["min", "mode", "max"],
    "Beta Scaled":    ["min", "max", "alpha", "beta"],
}


# ─────────────────────────────────────────────────────────────────────────────
# SAFE MATH
# ─────────────────────────────────────────────────────────────────────────────
def clamp(v, lo, hi):
    if not math.isfinite(v):
        return lo
    return max(lo, min(hi, v))


def safe_div(a, b, fb=0.0):
    if not b or not math.isfinite(b):
        return fb
    r = a / b
    return r if math.isfinite(r) else fb


def safe_pow(b, e, fb=0.0):
    try:
        r = b ** e
        return r if math.isfinite(r) else fb
    except Exception:
        return fb


# ─────────────────────────────────────────────────────────────────────────────
# DISTRIBUTIONS (vectorised with numpy)
# ─────────────────────────────────────────────────────────────────────────────
def sample_dist_array(cfg: dict, n: int, param_key: str) -> np.ndarray:
    """Sample n values from the distribution defined in cfg."""
    dist  = cfg.get("dist", "Normal")
    mean  = float(cfg.get("mean") or 0)
    std   = float(cfg.get("std") or max(abs(mean) * 0.1, 1))
    lo    = float(cfg.get("min") if cfg.get("min") not in ("", None) else mean - 3 * std)
    hi    = float(cfg.get("max") if cfg.get("max") not in ("", None) else mean + 3 * std)
    mode  = float(cfg.get("mode") if cfg.get("mode") not in ("", None) else mean)
    alpha = float(cfg.get("alpha") if cfg.get("alpha") not in ("", None) else 2)
    beta  = float(cfg.get("beta")  if cfg.get("beta")  not in ("", None) else 2)

    rng = np.random.default_rng()

    if dist == "Normal":
        samples = rng.normal(mean, std, n)

    elif dist == "Lognormal":
        sig2 = std ** 2
        mu_ln = math.log(mean ** 2 / math.sqrt(sig2 + mean ** 2)) if mean > 0 else 0
        sg_ln = math.sqrt(math.log(1 + (std / max(abs(mean), 1e-10)) ** 2))
        samples = np.exp(rng.normal(mu_ln, sg_ln, n))

    elif dist == "Uniform":
        samples = rng.uniform(lo, hi, n)

    elif dist == "Triangular":
        span = hi - lo
        if span <= 0:
            samples = np.full(n, lo)
        else:
            c = clamp((mode - lo) / span, 0, 1)
            samples = rng.triangular(lo, lo + c * span, hi, n)

    elif dist == "Truncated Normal":
        a_sc = (lo - mean) / max(std, 1e-10)
        b_sc = (hi - mean) / max(std, 1e-10)
        samples = stats.truncnorm.rvs(a_sc, b_sc, loc=mean, scale=std, size=n)

    elif dist == "PERT":
        pm = (lo + 4 * mode + hi) / 6
        ps = (hi - lo) / 6
        if ps < 1e-10:
            samples = np.full(n, pm)
        else:
            pa = ((pm - lo) / (hi - lo)) * (((pm - lo) * (hi - pm)) / ps ** 2 - 1)
            pb = pa * (hi - pm) / max(pm - lo, 1e-10)
            pa = max(0.01, pa)
            pb = max(0.01, pb)
            samples = lo + rng.beta(pa, pb, n) * (hi - lo)

    elif dist == "Beta Scaled":
        samples = lo + rng.beta(max(0.01, alpha), max(0.01, beta), n) * (hi - lo)

    else:
        samples = np.full(n, mean)

    # Apply published bounds
    r = PARAM_RANGES.get(param_key)
    if r:
        samples = np.clip(samples, r["min"], r["max"])

    return np.where(np.isfinite(samples), samples, mean)


# ─────────────────────────────────────────────────────────────────────────────
# CORRELATED INPUT SAMPLING (v2.0) — Iman & Conover (1982) rank correlation
# ─────────────────────────────────────────────────────────────────────────────
# Default correlation "hints" — pairs with a well-documented physical link.
# Users can override any of these, or add further pairs, from the UI.
DEFAULT_CORR_PAIRS = {
    ("UCS", "GSI"): 0.5,   # stronger intact rock tends to occur in better-quality masses
    ("Jr",  "Ja"):  -0.4,  # rougher joints (high Jr) tend to be less altered (low Ja)
}


def _nearest_pd_correlation(mat: np.ndarray) -> np.ndarray:
    """Project a symmetric matrix with unit diagonal onto the nearest
    positive-semi-definite correlation matrix (clips negative eigenvalues).
    This guards against a user-supplied correlation matrix that is not a
    valid (consistent) correlation structure."""
    mat = (mat + mat.T) / 2.0
    eigval, eigvec = np.linalg.eigh(mat)
    eigval_clipped = np.clip(eigval, 1e-8, None)
    fixed = eigvec @ np.diag(eigval_clipped) @ eigvec.T
    d = np.sqrt(np.diag(fixed))
    d[d == 0] = 1.0
    fixed = fixed / np.outer(d, d)
    np.fill_diagonal(fixed, 1.0)
    return fixed


def build_correlation_matrix(keys: List[str], corr_pairs: Dict[Tuple[str, str], float]) -> np.ndarray:
    """Assemble a k×k correlation matrix for the given active parameter keys
    from a dict of pairwise target correlations {(key_a, key_b): rho}."""
    k = len(keys)
    idx = {key: i for i, key in enumerate(keys)}
    mat = np.eye(k)
    for (a, b), rho in corr_pairs.items():
        if a in idx and b in idx and a != b:
            i, j = idx[a], idx[b]
            rho = float(clamp(rho, -0.999, 0.999))
            mat[i, j] = rho
            mat[j, i] = rho
    return _nearest_pd_correlation(mat)


def apply_iman_conover(indep_samples: Dict[str, np.ndarray], keys: List[str],
                        corr_matrix: np.ndarray) -> Dict[str, np.ndarray]:
    """Impose a target rank-correlation structure on a set of already-sampled
    (independent) marginal distributions, using the Iman & Conover (1982)
    method: correlated standard-normal "scores" are generated via a Cholesky
    decomposition of the target correlation matrix, and each parameter's
    independent samples are then re-ordered (not re-sampled) to match the
    rank order implied by those scores. Because samples are only permuted,
    each parameter's original marginal distribution is preserved exactly;
    only the joint rank-dependence structure changes.
    """
    k = len(keys)
    n = len(indep_samples[keys[0]])
    if k < 2 or n < 2:
        return indep_samples

    try:
        L = np.linalg.cholesky(corr_matrix)
    except np.linalg.LinAlgError:
        corr_matrix = _nearest_pd_correlation(corr_matrix)
        L = np.linalg.cholesky(corr_matrix)

    rng = np.random.default_rng()
    Z = rng.standard_normal((n, k)) @ L.T          # correlated normal scores
    rank_of_score = np.argsort(np.argsort(Z, axis=0), axis=0)  # 0..n-1 per column

    out = dict(indep_samples)
    for j, key in enumerate(keys):
        sorted_vals = np.sort(indep_samples[key])
        out[key] = sorted_vals[rank_of_score[:, j]]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SPATIAL VARIABILITY / 1-D RANDOM FIELDS (v2.0)
# Methodology: exponential (Markov) autocorrelation function discretised over
# the tunnel alignment and generated via Cholesky decomposition, following the
# random-field approach summarised by Wang & Cao (2014). Spatial averaging
# over a given window uses Vanmarcke's (1977) variance reduction function.
# ─────────────────────────────────────────────────────────────────────────────
def variance_reduction_gamma(window: float, theta: float) -> float:
    """Vanmarcke (1977) variance reduction function Γ(window) for a 1-D
    exponential autocorrelation function with scale of fluctuation `theta`.
    Returns the factor by which point variance is reduced when averaged over
    `window` (same length units as theta)."""
    if window <= 0:
        return 1.0
    t = window / max(theta, 1e-9)
    if t < 1e-6:
        return 1.0
    gamma = (2 * theta ** 2 / window ** 2) * (t - 1 + math.exp(-t))
    return float(clamp(gamma, 0.0, 1.0))


def generate_random_field(mean: float, std: float, corr_length: float,
                           tunnel_length: float, segment_length: float,
                           n_realizations: int, lo: Optional[float] = None,
                           hi: Optional[float] = None) -> np.ndarray:
    """Generate `n_realizations` 1-D random field realisations of a rock mass
    property along a tunnel alignment, with an exponential (Markov)
    autocorrelation function of scale of fluctuation `corr_length`.

    Returns an array of shape (n_realizations, n_segments).
    """
    n_seg = max(2, int(math.ceil(tunnel_length / max(segment_length, 1e-6))))
    x = np.arange(n_seg) * segment_length
    d = np.abs(x[:, None] - x[None, :])
    rho = np.exp(-d / max(corr_length, 1e-6))
    rho = _nearest_pd_correlation(rho)

    L = np.linalg.cholesky(rho)
    rng = np.random.default_rng()
    Z = rng.standard_normal((n_realizations, n_seg)) @ L.T
    field = mean + std * Z
    if lo is not None or hi is not None:
        field = np.clip(field, lo if lo is not None else -np.inf,
                         hi if hi is not None else np.inf)
    return field


# ─────────────────────────────────────────────────────────────────────────────
# ROCK MASS CALCULATIONS (vectorised)
# ─────────────────────────────────────────────────────────────────────────────
def hoek_brown(GSI, mi, UCS, D):
    """Returns mb, s, a arrays."""
    gsi = np.clip(GSI, 1, 100)
    mi_ = np.clip(mi,  0.5, 40)
    d_  = np.clip(D,   0,   1)

    mb  = mi_ * np.exp((gsi - 100) / np.maximum(0.1, 28 - 14 * d_))
    s   = np.exp((gsi - 100) / np.maximum(0.1, 9 - 3 * d_))
    a   = 0.5 + (1 / 6) * (np.exp(-gsi / 15) - np.exp(-20 / 3))

    mb  = np.where(np.isfinite(mb), np.maximum(0, mb), 0)
    s   = np.where(np.isfinite(s),  np.clip(s, 0, 1),  0)
    a   = np.where(np.isfinite(a),  np.clip(a, 0.5, 0.65), 0.5)
    return mb, s, a


def calc_em_hd(GSI, UCS, D):
    gsi = np.clip(GSI, 1, 100)
    ucs = np.clip(UCS, 0.1, 1000)
    d_  = np.clip(D, 0, 1)
    v   = (ucs / 100) * np.exp((gsi - 11 * d_) / 36) * 0.02
    return np.where(np.isfinite(v), np.maximum(0, v), 0)


def calc_em_sp(rmr):
    v = 10 ** ((np.clip(rmr, 0, 100) - 10) / 40)
    return np.where(np.isfinite(v), np.maximum(0, v), 0)


def calc_ei(MR, UCS):
    return np.maximum(0, (np.clip(MR, 1, 2000) * np.clip(UCS, 0.1, 1000)) / 1000)


def calc_rmr(UCS, RQD, sp, cond, gw):
    u = np.clip(UCS, 0, 250)
    r = np.clip(RQD, 0, 100)
    s = np.clip(sp,  1, 100000)

    r1 = np.where(u > 250, 15, np.where(u > 100, 12, np.where(u > 50, 7,
         np.where(u > 25, 4, np.where(u > 5, 2, np.where(u > 1, 1, 0))))))
    r2 = np.where(r > 90, 20, np.where(r > 75, 17, np.where(r > 50, 13,
         np.where(r > 25, 8, 3))))
    r3 = np.where(s > 2000, 20, np.where(s > 600, 15, np.where(s > 200, 10,
         np.where(s > 60, 8, 5))))

    return np.clip(r1 + r2 + r3 + np.clip(cond.astype(float), 0, 30) + np.clip(gw.astype(float), 0, 15), 0, 100)


def rmr_class(r: float) -> str:
    if r >= 81: return "I"
    if r >= 61: return "II"
    if r >= 41: return "III"
    if r >= 21: return "IV"
    return "V"


def rmr_label(c: str) -> str:
    return {"I": "Very Good", "II": "Good", "III": "Fair", "IV": "Poor", "V": "Very Poor"}.get(c, "")


def calc_q(RQD, Jn, Jr, Ja, Jw, SRF):
    rqd = np.clip(RQD, 0, 100)
    jn  = np.maximum(0.5, Jn)
    jr  = np.clip(Jr, 0.5, 4)
    ja  = np.maximum(0.75, Ja)
    jw  = np.clip(Jw, 0.05, 1)
    srf = np.maximum(0.5, SRF)
    v   = (rqd / jn) * (jr / ja) * (jw / srf)
    return np.where(np.isfinite(v), np.maximum(0, v), 0)


def calc_rms(UCS, GSI, mi, D):
    _, s, a = hoek_brown(GSI, mi, UCS, D)
    ucs = np.clip(UCS, 0.1, 1000)
    v   = ucs * np.where(s >= 0, s ** a, 0)
    return np.where(np.isfinite(v), np.maximum(0, v), 0)


def calc_cf(UCS, GSI, mi, D):
    """Returns cohesion and friction arrays."""
    mb, s, a = hoek_brown(GSI, mi, UCS, D)
    ucs = np.clip(UCS, 0.1, 1000)
    s3  = 0.1 * ucs
    inner = np.maximum(1e-12, mb * s3 / ucs + s)
    denom = 6 * a * mb * inner ** (a - 1)
    numer = 2 * (1 + a) * (2 + a)
    total = numer + denom
    total = np.where(total <= 0, 1e-10, total)

    sin_phi = np.clip(denom / total, -0.9999, 0.9999)
    phi     = np.arcsin(sin_phi) * 180 / math.pi

    sig1 = ucs * inner ** a
    phi_r = np.clip(phi, 0, 89) * math.pi / 180
    denom2 = 2 * np.maximum(1e-10, np.tan(math.pi / 4 + np.clip(phi, 0, 89) * math.pi / 360))
    coh    = (sig1 - s3 * np.tan(phi_r)) / denom2

    cohesion = np.where(np.isfinite(coh), np.maximum(0, coh), 0)
    friction = np.where(np.isfinite(phi), np.maximum(0, phi), 0)
    return cohesion, friction


def calc_support_pressure(rmr, Q_val, Jn, Jr, UCS, tunnel_diam=5.0):
    r   = np.clip(rmr,    0, 100)
    q   = np.maximum(0.001, Q_val)
    jn  = np.maximum(0.5, Jn)
    jr  = np.maximum(0.5, Jr)
    ucs = np.clip(UCS, 0.25, 250)
    B   = clamp(tunnel_diam, 1, 30)

    # Terzaghi: Ht factor from RMR class
    Ht = np.where(r >= 81, 0.0,
         np.where(r >= 61, 0.25 * B,
         np.where(r >= 41, 0.5  * B,
         np.where(r >= 21, 1.0  * B, 1.5  * B))))

    Pv_t = GAMMA_ROCK * Ht
    Pv_b = (2 * np.sqrt(jn) * ucs) / (3 * jr * np.maximum(0.001, q ** (1/3)))
    Pv_r = GAMMA_ROCK * B * (100 - r) / 100

    return (
        np.where(np.isfinite(Pv_t), np.maximum(0, Pv_t), 0),
        np.where(np.isfinite(Pv_b), np.maximum(0, Pv_b), 0),
        np.where(np.isfinite(Pv_r), np.maximum(0, Pv_r), 0),
    )


def calc_tunnel_convergence(UCS, GSI, mi, D, MR, tunnel_radius=2.5, insitu_stress=5.0):
    ri  = max(0.5, tunnel_radius)
    P0  = max(0.1, insitu_stress)
    ucs = np.clip(UCS, 0.25, 250)
    em  = np.maximum(0.01, calc_ei(np.clip(MR, 50, 1000), ucs))

    _, s, a = hoek_brown(GSI, mi, ucs, D)
    scm = np.clip(ucs * np.where(s >= 0, s ** a, 0.001), 0.001, ucs)

    coh, phi = calc_cf(ucs, GSI, mi, D)
    phi_r   = np.clip(phi, 5, 85) * math.pi / 180
    sin_phi = np.sin(phi_r)

    Em_MPa   = em * 1000
    ui_kirsch = np.maximum(0, (P0 * ri) / (2 * Em_MPa) * 1000)

    denom_rp = scm * (1 + sin_phi)
    base     = np.where(denom_rp > 0, (2 * P0) / denom_rp, 1)
    exp_rp   = np.where((1 - sin_phi) > 0.001, 0.5 / np.maximum(0.01, 1 - sin_phi), 1)
    rp       = ri * np.where(base > 0, base ** exp_rp, 1)
    rp       = np.clip(rp, ri, ri * 20)

    return (
        np.where(np.isfinite(ui_kirsch), ui_kirsch, 0),
        np.where(np.isfinite(rp),        rp,        ri),
    )


def calc_sigma_cm_generalized(UCS, GSI, mi, D):
    """Hoek's generalized rock mass strength sigma_cm (Hoek, Carranza-Torres &
    Corkum 2002), representing the average rock mass strength over the
    confining stress range relevant to a typical excavation — this is the
    quantity used in the Hoek-Brown based CCM curves (calc_tunnel_convergence_hb),
    and is distinct from the simpler sigma_ci * s^a "uniaxial" value (Rms output).

        sigma_cm = sigma_ci * [(mb + 4s - a(mb - 8s)) * (mb/4 + s)^(a-1)]
                   / [2*(1+a)*(2+a)]
    """
    mb, s, a = hoek_brown(GSI, mi, UCS, D)
    ucs = np.clip(UCS, 0.1, 1000)
    inner = np.maximum(1e-12, mb / 4 + s)
    numer = (mb + 4 * s - a * (mb - 8 * s)) * safe_pow_arr(inner, a - 1)
    denom = 2 * (1 + a) * (2 + a)
    v = ucs * numer / np.maximum(1e-12, denom)
    return np.where(np.isfinite(v), np.maximum(0, v), 0)


def calc_tunnel_convergence_hb(UCS, GSI, mi, D, tunnel_radius=2.5, insitu_stress=5.0,
                                support_pressure_ratio=0.0):
    """Extended CCM using the Hoek-Brown based ground reaction curves.

    These are the widely-used closed-form curve fits (Duncan Fama 1993, as
    reported in Hoek (2000) "Big Tunnels in Bad Rock" and Hoek's "Practical
    Rock Engineering", Ch. 12 "Tunnels in Weak Rock") to results generated
    from the rigorous Hoek-Brown elasto-plastic solution of Carranza-Torres &
    Fairhurst (1999):

        eps%  = 0.2 * (sigma_cm/p0)^(-2 + 2.4*(pi/p0))            [strain, %]
        rp/ri = (1.25 - 0.625*(pi/p0)) * (sigma_cm/p0)^((pi/p0) - 0.57)

    where sigma_cm is the Hoek-Brown rock mass strength (sigma_ci * s^a) and
    pi/p0 is the ratio of internal support pressure to in-situ stress. These
    fits target weak/squeezing ground (sigma_cm/p0 typically well below 1);
    for stronger ground the elastic-perfectly-plastic Mohr-Coulomb-based
    "Simplified" CCM already implemented is more broadly applicable, so the
    two methods are offered as alternatives rather than one replacing the
    other. If the rock is elastic (support pressure at/above the classical
    Mohr-Coulomb critical pressure) the plastic-zone terms are suppressed.
    """
    ri  = max(0.5, tunnel_radius)
    P0  = max(0.1, insitu_stress)
    ucs = np.clip(UCS, 0.25, 250)
    pi_ratio = float(clamp(support_pressure_ratio, 0.0, 0.95))

    sigma_cm = calc_sigma_cm_generalized(ucs, GSI, mi, D)   # Hoek 2002 generalized rock mass strength
    ratio = np.clip(safe_div_arr(sigma_cm, P0), 1e-6, 1e6)

    eps_pct = 0.2 * safe_pow_arr(ratio, -2 + 2.4 * pi_ratio)
    eps_pct = np.clip(eps_pct, 0, 50)                    # cap unrealistic extrapolation
    ui_hb = (eps_pct / 100.0) * ri * 1000.0              # mm

    rp_ratio = (1.25 - 0.625 * pi_ratio) * safe_pow_arr(ratio, pi_ratio - 0.57)
    rp_ratio = np.maximum(1.0, rp_ratio)                 # rp cannot be < ri
    rp_ratio = np.clip(rp_ratio, 1.0, 20.0)
    rp_hb = rp_ratio * ri

    return (
        np.where(np.isfinite(ui_hb), np.maximum(0, ui_hb), 0),
        np.where(np.isfinite(rp_hb), rp_hb, ri),
    )


def safe_div_arr(a: np.ndarray, b, fb=1e-6) -> np.ndarray:
    b_arr = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = a / np.where(b_arr == 0, fb, b_arr)
    return np.where(np.isfinite(r), r, fb)


def safe_pow_arr(base: np.ndarray, exp) -> np.ndarray:
    with np.errstate(invalid="ignore", over="ignore"):
        r = np.power(np.clip(base, 1e-9, None), exp)
    return np.where(np.isfinite(r), r, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# RELIABILITY
# ─────────────────────────────────────────────────────────────────────────────
def normal_cdf(x: float) -> float:
    return stats.norm.cdf(x)


def calc_reliability(Rms_arr: np.ndarray, stress_arr: np.ndarray):
    FS = np.where(stress_arr > 0, Rms_arr / np.maximum(0.001, stress_arr), 0)
    valid = FS[np.isfinite(FS) & (FS > 0)]
    if len(valid) == 0:
        return {"FS": np.array([]), "PoF": 0, "beta": 0, "muFS": 0, "sigFS": 0}
    muFS   = float(valid.mean())
    sigFS  = float(valid.std())
    PoF    = float((valid < 1.0).sum() / len(valid))
    beta   = (muFS - 1) / sigFS if sigFS > 0 else (99 if muFS > 1 else -99)
    return {"FS": valid, "PoF": PoF, "beta": float(beta), "muFS": muFS, "sigFS": sigFS}


def calc_form(mu_rms, sig_rms, mu_stress, sig_stress):
    g_mean  = mu_rms - mu_stress
    sigma_g = math.sqrt(sig_rms ** 2 + sig_stress ** 2)
    if sigma_g < 1e-10:
        return {"beta_form": 99 if g_mean > 0 else -99, "PoF_form": 0 if g_mean > 0 else 1}
    beta_f = g_mean / sigma_g
    PoF_f  = normal_cdf(-beta_f)
    return {
        "beta_form": float(beta_f) if math.isfinite(beta_f) else 0,
        "PoF_form":  float(PoF_f)  if math.isfinite(PoF_f)  else 0.5,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STATISTICS
# ─────────────────────────────────────────────────────────────────────────────
def compute_stats(arr: np.ndarray) -> dict:
    empty = {k: 0.0 for k in ["mean", "std", "min", "max", "p10", "p25", "p50", "p75", "p90", "p95"]}
    if arr is None or len(arr) == 0:
        return empty
    safe = arr[np.isfinite(arr)]
    if len(safe) == 0:
        return empty
    return {
        "mean": float(safe.mean()),
        "std":  float(safe.std()),
        "min":  float(safe.min()),
        "max":  float(safe.max()),
        "p10":  float(np.percentile(safe, 10)),
        "p25":  float(np.percentile(safe, 25)),
        "p50":  float(np.percentile(safe, 50)),
        "p75":  float(np.percentile(safe, 75)),
        "p90":  float(np.percentile(safe, 90)),
        "p95":  float(np.percentile(safe, 95)),
    }


def build_hist(arr: np.ndarray, bins: int = 22) -> List[dict]:
    if arr is None or len(arr) == 0:
        return []
    safe = arr[np.isfinite(arr)]
    if len(safe) == 0:
        return []
    counts, edges = np.histogram(safe, bins=bins)
    total = len(safe)
    return [
        {"lo": float(edges[i]), "hi": float(edges[i + 1]),
         "count": int(counts[i]), "pct": float(counts[i] / total * 100)}
        for i in range(bins)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SENSITIVITY — Spearman rank correlation
# ─────────────────────────────────────────────────────────────────────────────
def sensitivity_corr(inp: dict, out_arr: np.ndarray) -> List[dict]:
    results = []
    for key, vals in inp.items():
        v = np.array(vals)
        if len(v) == 0 or v.std() == 0:
            corr = 0.0
        else:
            corr, _ = stats.spearmanr(v, out_arr)
            corr = float(corr) if math.isfinite(corr) else 0.0
        results.append({"key": key, "corr": corr})
    results.sort(key=lambda x: abs(x["corr"]), reverse=True)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# ANN (pure numpy, no external ML libs)
# ─────────────────────────────────────────────────────────────────────────────
class NeuralNetwork:
    def __init__(self, layer_sizes: List[int]):
        self.sizes = layer_sizes
        self.W: List[np.ndarray] = []
        self.B: List[np.ndarray] = []
        for i in range(1, len(layer_sizes)):
            scale = math.sqrt(2 / layer_sizes[i - 1])
            self.W.append(np.random.randn(layer_sizes[i], layer_sizes[i - 1]) * scale)
            self.B.append(np.zeros(layer_sizes[i]))

    @staticmethod
    def relu(x: np.ndarray) -> np.ndarray:
        return np.maximum(0, x)

    @staticmethod
    def relu_d(x: np.ndarray) -> np.ndarray:
        return (x > 0).astype(float)

    def forward(self, x: np.ndarray) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        acts = [x]
        pres = []
        for i, (W, b) in enumerate(zip(self.W, self.B)):
            pre = W @ acts[-1] + b
            pres.append(pre)
            is_last = (i == len(self.W) - 1)
            acts.append(pre if is_last else self.relu(pre))
        return acts, pres

    def predict_batch(self, X: np.ndarray) -> np.ndarray:
        out = []
        for x in X:
            acts, _ = self.forward(x)
            out.append(acts[-1])
        return np.array(out)

    def train_step(self, X: np.ndarray, Y: np.ndarray, lr: float) -> float:
        """Mini-batch SGD. Returns MSE."""
        total_loss = 0.0
        dW = [np.zeros_like(w) for w in self.W]
        dB = [np.zeros_like(b) for b in self.B]

        for x, y in zip(X, Y):
            acts, pres = self.forward(x)
            L = len(self.W)
            delta = acts[L] - y
            total_loss += float(np.sum(delta ** 2)) / len(y)

            for l in range(L - 1, -1, -1):
                prev = acts[l]
                dW[l] += np.outer(delta, prev)
                dB[l] += delta
                if l > 0:
                    delta = (self.W[l].T @ delta) * self.relu_d(pres[l - 1])

        n = len(X)
        for l in range(len(self.W)):
            self.W[l] -= lr * dW[l] / n
            self.B[l] -= lr * dB[l] / n
        return total_loss / n


def norm_data(data: np.ndarray):
    mins = data.min(axis=0)
    maxs = data.max(axis=0)
    rng  = np.where(maxs - mins < 1e-10, 1, maxs - mins)
    return (data - mins) / rng, mins, maxs


def r2_score(actual: np.ndarray, pred: np.ndarray) -> float:
    ss_res = np.sum((actual - pred) ** 2)
    ss_tot = np.sum((actual - actual.mean()) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def rmse_score(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - pred) ** 2)))


def mae_score(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - pred)))


# ─────────────────────────────────────────────────────────────────────────────
# LINEAR & AUTO-REGRESSION TOOLS (v2.0) — "Other Machine Learning Outputs"
# ─────────────────────────────────────────────────────────────────────────────
def fit_linear_regression(X: np.ndarray, y: np.ndarray, feature_names: List[str]) -> dict:
    """Ordinary least-squares multiple linear regression via numpy lstsq.
    Returns intercept, coefficients, R2, RMSE and a human-readable formula
    string the user can re-use for continuous, on-site estimation."""
    n = X.shape[0]
    A = np.column_stack([np.ones(n), X])
    coef, residuals, rank, sv = np.linalg.lstsq(A, y, rcond=None)
    intercept = float(coef[0])
    betas = coef[1:]
    pred = A @ coef
    r2 = r2_score(y, pred)
    rmse = rmse_score(y, pred)
    mae = mae_score(y, pred)

    terms = [f"{b:+.5g}*{name}" for b, name in zip(betas, feature_names)]
    formula = f"y = {intercept:.5g} " + " ".join(terms)

    return {
        "intercept": intercept,
        "coefficients": dict(zip(feature_names, betas.tolist())),
        "r2": r2, "rmse": rmse, "mae": mae,
        "formula": formula,
        "predicted": pred,
        "actual": y,
    }


def fit_yule_walker_ar(series: np.ndarray, order: int = 1) -> dict:
    """Fit an AR(p) model to a (spatial or sequential) series using the
    Yule-Walker equations solved from the sample autocorrelation function.
    Returns AR coefficients, the mean, noise variance, and a formula string.
    Useful for the spatially-correlated segment values produced in the
    Spatial Variability tab (treating tunnel chainage as the sequence index).
    """
    x = np.asarray(series, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    p = max(1, min(order, n - 2))
    mean = float(x.mean())
    xc = x - mean
    var0 = float(np.dot(xc, xc) / n)

    # Sample autocorrelation r_0..r_p
    r = np.array([np.dot(xc[:n - k], xc[k:]) / n for k in range(p + 1)])
    if var0 <= 1e-12:
        return {"order": p, "phi": [0.0] * p, "mean": mean, "noise_var": 0.0,
                "formula": f"y_t = {mean:.5g} (series has ~zero variance)"}

    R = np.array([[r[abs(i - j)] for j in range(p)] for i in range(p)])
    try:
        phi = np.linalg.solve(R, r[1:p + 1])
    except np.linalg.LinAlgError:
        phi = np.linalg.lstsq(R, r[1:p + 1], rcond=None)[0]

    noise_var = max(0.0, var0 - float(np.dot(phi, r[1:p + 1])))

    terms = " ".join([f"{c:+.5g}*(y_t-{k+1} - mean)" for k, c in enumerate(phi)])
    formula = f"y_t = {mean:.5g} {terms}"

    # In-sample one-step-ahead fit quality
    if n > p:
        pred = np.array([mean + np.dot(phi, (x[t - p:t][::-1] - mean)) for t in range(p, n)])
        actual = x[p:]
        r2 = r2_score(actual, pred)
    else:
        r2 = 0.0

    return {
        "order": p, "phi": phi.tolist(), "mean": mean,
        "noise_var": noise_var, "formula": formula, "r2": r2,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ACTIVE PARAM RESOLUTION
# ─────────────────────────────────────────────────────────────────────────────
def get_active_params(out_enabled: dict, em_mode: str) -> set:
    deps = dict(OUTPUT_DEPS)
    # Override Em deps with mode-specific deps
    if "Em" in out_enabled and out_enabled["Em"]:
        deps["Em"] = EM_DEPS.get(em_mode, EM_DEPS["HD"])
    needed = set()
    for key, on in out_enabled.items():
        if on:
            for pk in deps.get(key, []):
                needed.add(pk)
    return needed


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────
def _default_param_cfg():
    return {"dist": "Normal", "mean": "", "std": "", "min": "", "max": "", "mode": "", "alpha": "2", "beta": "2"}


def _default_out_enabled():
    return {o["key"]: (o["group"] == "core") for o in ALL_OUTPUTS}


def init_session():
    if "params" not in st.session_state:
        st.session_state.params = {p["key"]: _default_param_cfg() for p in ALL_PARAMS}
    if "iters" not in st.session_state:
        st.session_state.iters = 1000
    if "out_enabled" not in st.session_state:
        st.session_state.out_enabled = _default_out_enabled()
    if "em_mode" not in st.session_state:
        st.session_state.em_mode = "HD"
    if "results" not in st.session_state:
        st.session_state.results = None
    if "project_name" not in st.session_state:
        st.session_state.project_name = "My Project"
    if "tunnel_diam" not in st.session_state:
        st.session_state.tunnel_diam = 5.0
    if "tunnel_radius" not in st.session_state:
        st.session_state.tunnel_radius = 2.5
    if "insitu_stress" not in st.session_state:
        st.session_state.insitu_stress = 5.0
    if "applied_stress_ratio" not in st.session_state:
        st.session_state.applied_stress_ratio = 0.3
    # ANN
    if "ann_target" not in st.session_state:
        st.session_state.ann_target = "Q"
    if "ann_split" not in st.session_state:
        st.session_state.ann_split = 80
    if "ann_hidden" not in st.session_state:
        st.session_state.ann_hidden = 2
    if "ann_neurons" not in st.session_state:
        st.session_state.ann_neurons = 16
    if "ann_epochs" not in st.session_state:
        st.session_state.ann_epochs = 100
    if "ann_lr" not in st.session_state:
        st.session_state.ann_lr = 0.01
    if "ann_batch" not in st.session_state:
        st.session_state.ann_batch = 32
    # v2.0 — Correlated sampling
    if "corr_pairs" not in st.session_state:
        st.session_state.corr_pairs = dict(DEFAULT_CORR_PAIRS)
    if "corr_enabled" not in st.session_state:
        st.session_state.corr_enabled = False
    # v2.0 — Extended CCM
    if "ccm_method" not in st.session_state:
        st.session_state.ccm_method = "MC"   # "MC" simplified Mohr-Coulomb | "HB" Hoek-Brown
    if "support_pressure_ratio" not in st.session_state:
        st.session_state.support_pressure_ratio = 0.0
    # v2.0 — Spatial variability
    if "tunnel_length" not in st.session_state:
        st.session_state.tunnel_length = 500.0
    if "corr_length" not in st.session_state:
        st.session_state.corr_length = 20.0
    if "segment_length" not in st.session_state:
        st.session_state.segment_length = 5.0
    if "spatial_param" not in st.session_state:
        st.session_state.spatial_param = "RMR"
    if "spatial_n_real" not in st.session_state:
        st.session_state.spatial_n_real = 200
    if "spatial_results" not in st.session_state:
        st.session_state.spatial_results = None
    # v2.0 — Regression tools
    if "reg_target" not in st.session_state:
        st.session_state.reg_target = "Q"
    if "reg_features" not in st.session_state:
        st.session_state.reg_features = []
    if "reg_result" not in st.session_state:
        st.session_state.reg_result = None
    if "ar_order" not in st.session_state:
        st.session_state.ar_order = 2
    if "ar_result" not in st.session_state:
        st.session_state.ar_result = None
    # v2.0 — Construction monitoring (beta)
    if "monitoring_data" not in st.session_state:
        st.session_state.monitoring_data = None
    if "monitoring_results" not in st.session_state:
        st.session_state.monitoring_results = None


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def run_simulation(params: dict, iters: int, out_enabled: dict, em_mode: str,
                   tunnel_diam: float, tunnel_radius: float,
                   insitu_stress: float, applied_stress_ratio: float,
                   corr_enabled: bool = False, corr_pairs: Optional[dict] = None,
                   ccm_method: str = "MC", support_pressure_ratio: float = 0.0) -> dict:
    n = max(10, iters)
    active_params = get_active_params(out_enabled, em_mode)

    # Sample all active inputs (independent marginals)
    inp = {}
    for p in ALL_PARAMS:
        key = p["key"]
        if key in active_params:
            inp[key] = sample_dist_array(params[key], n, key)
        else:
            inp[key] = np.zeros(n)

    # v2.0 — Correlated Input Sampling (Iman-Conover)
    applied_corr_matrix = None
    if corr_enabled and corr_pairs:
        act_keys = [k for k in ALL_PARAM_KEYS if k in active_params]
        if len(act_keys) > 1:
            applied_corr_matrix = build_correlation_matrix(act_keys, corr_pairs)
            corr_result = apply_iman_conover(
                {k: inp[k] for k in act_keys}, act_keys, applied_corr_matrix)
            inp.update(corr_result)

    def g(k): return inp[k]  # shorthand

    # ── Core calculations ──
    Q_arr   = calc_q(g("RQD"), g("Jn"), g("Jr"), g("Ja"), g("Jw"), g("SRF"))
    RMR_arr = calc_rmr(g("UCS"), g("RQD"), g("JointSpacing"), g("JointCondition"), g("Groundwater"))
    mb_arr, s_arr, a_arr = hoek_brown(g("GSI"), g("mi"), g("UCS"), g("D"))

    if out_enabled.get("Em"):
        Em_arr = calc_em_hd(g("GSI"), g("UCS"), g("D")) if em_mode == "HD" else calc_em_sp(RMR_arr)
    else:
        Em_arr = np.zeros(n)

    Ei_arr  = calc_ei(g("MR"), g("UCS"))
    Rms_arr = calc_rms(g("UCS"), g("GSI"), g("mi"), g("D"))
    coh_arr, fri_arr = calc_cf(g("UCS"), g("GSI"), g("mi"), g("D"))

    # ── Support Pressure ──
    Pv_t_arr = Pv_b_arr = Pv_r_arr = np.zeros(n)
    if any(out_enabled.get(k) for k in ["Pv_terzaghi", "Pv_barton", "Pv_rmr"]):
        Pv_t_arr, Pv_b_arr, Pv_r_arr = calc_support_pressure(
            RMR_arr, Q_arr, g("Jn"), g("Jr"), g("UCS"), tunnel_diam)

    # ── Tunnel Convergence ──
    ui_arr = rp_arr = np.zeros(n)
    if any(out_enabled.get(k) for k in ["ui_kirsch", "rp_plastic"]):
        if ccm_method == "HB":
            ui_arr, rp_arr = calc_tunnel_convergence_hb(
                g("UCS"), g("GSI"), g("mi"), g("D"), tunnel_radius, insitu_stress,
                support_pressure_ratio)
        else:
            ui_arr, rp_arr = calc_tunnel_convergence(
                g("UCS"), g("GSI"), g("mi"), g("D"), g("MR"), tunnel_radius, insitu_stress)

    # ── Reliability / FS ──
    rng = np.random.default_rng()
    stress_arr = np.maximum(0.001, insitu_stress * (0.5 + rng.random(n) * applied_stress_ratio))
    FS_arr = np.where(stress_arr > 0, Rms_arr / np.maximum(0.001, stress_arr), 0)

    out = {
        "Q":           Q_arr   if out_enabled.get("Q")    else np.zeros(n),
        "RMR":         RMR_arr if out_enabled.get("RMR")  else np.zeros(n),
        "Em":          Em_arr,
        "Ei":          Ei_arr  if out_enabled.get("Ei")   else np.zeros(n),
        "Rms":         Rms_arr if out_enabled.get("Rms")  else np.zeros(n),
        "mb":          mb_arr  if out_enabled.get("mb")   else np.zeros(n),
        "s":           s_arr   if out_enabled.get("s")    else np.zeros(n),
        "a":           a_arr   if out_enabled.get("a")    else np.zeros(n),
        "cohesion":    coh_arr if out_enabled.get("cohesion") else np.zeros(n),
        "friction":    fri_arr if out_enabled.get("friction") else np.zeros(n),
        "Pv_terzaghi": Pv_t_arr if out_enabled.get("Pv_terzaghi") else np.zeros(n),
        "Pv_barton":   Pv_b_arr if out_enabled.get("Pv_barton")   else np.zeros(n),
        "Pv_rmr":      Pv_r_arr if out_enabled.get("Pv_rmr")      else np.zeros(n),
        "ui_kirsch":   ui_arr  if out_enabled.get("ui_kirsch")  else np.zeros(n),
        "rp_plastic":  rp_arr  if out_enabled.get("rp_plastic") else np.zeros(n),
        "FS_dist":     FS_arr  if out_enabled.get("FS_dist")    else np.zeros(n),
    }

    # ── Statistics ──
    o_stats = {o["key"]: compute_stats(out[o["key"]]) for o in ALL_OUTPUTS}
    o_hist  = {o["key"]: build_hist(out[o["key"]]) for o in ALL_OUTPUTS}
    i_hist  = {p["key"]: build_hist(inp[p["key"]]) for p in ALL_PARAMS}

    # ── Sensitivity ──
    sensitivity = {}
    for o in ALL_OUTPUTS:
        sensitivity[o["key"]] = sensitivity_corr(inp, out[o["key"]])

    # ── Correlation matrix ──
    apk = list(active_params)
    corr_data = {}
    if len(apk) > 1:
        mat = np.column_stack([inp[k] for k in apk])
        corr_matrix, _ = stats.spearmanr(mat)
        if len(apk) == 2:
            corr_matrix = np.array([[1, corr_matrix], [corr_matrix, 1]])
        for i, pa in enumerate(apk):
            corr_data[pa] = {}
            for j, pb in enumerate(apk):
                corr_data[pa][pb] = float(corr_matrix[i, j]) if np.isfinite(corr_matrix[i, j]) else (1.0 if pa == pb else 0.0)

    # ── RMR distribution ──
    rmr_dist = {"I": 0, "II": 0, "III": 0, "IV": 0, "V": 0}
    if out_enabled.get("RMR"):
        for r in RMR_arr:
            rmr_dist[rmr_class(r)] += 1

    # ── Reliability ──
    rel_data = form_data = None
    if out_enabled.get("FS_dist"):
        rel_data = calc_reliability(Rms_arr, stress_arr)
        rms_st = o_stats.get("Rms", {})
        if rms_st.get("mean", 0) > 0:
            form_data = calc_form(rms_st["mean"], rms_st["std"], insitu_stress, insitu_stress * 0.15)

    return {
        "n": n,
        "out": out,
        "inp": inp,
        "o_stats": o_stats,
        "o_hist": o_hist,
        "i_hist": i_hist,
        "sensitivity": sensitivity,
        "corr_data": corr_data,
        "rmr_dist": rmr_dist,
        "out_enabled": dict(out_enabled),
        "em_mode": em_mode,
        "active_params": list(active_params),
        "reliability_data": rel_data,
        "form_data": form_data,
        "tunnel_diam": tunnel_diam,
        "tunnel_radius": tunnel_radius,
        "insitu_stress": insitu_stress,
        "applied_stress_ratio": applied_stress_ratio,
        "ann": None,
        "corr_enabled": corr_enabled,
        "applied_corr_matrix": applied_corr_matrix.tolist() if applied_corr_matrix is not None else None,
        "ccm_method": ccm_method,
        "support_pressure_ratio": support_pressure_ratio,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────────────────────────────────────
def export_excel(results: dict, active_out: List[dict], project_name: str) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        n = results["n"]
        o_stats = results["o_stats"]
        stat_cols = ["mean", "std", "min", "p10", "p25", "p50", "p75", "p90", "p95", "max"]

        # 1. Dashboard
        rows = [["ROCK MASS VARIABILITY ANALYSIS — Monte Carlo Simulation Report"],
                [f"Project: {project_name} | Iterations: {n:,} | Em: {EM_MODES[results['em_mode']]['label']}"],
                [],
                ["Output", "Unit"] + [s.upper() for s in stat_cols]]
        for o in active_out:
            s = o_stats[o["key"]]
            rows.append([o["label"], o.get("unit", "—")] + [round(s[f], 5) for f in stat_cols])
        pd.DataFrame(rows).to_excel(writer, sheet_name="Dashboard", index=False, header=False)

        # 2. Raw Samples (first 500)
        display_n = min(500, n)
        raw_rows = [[i + 1] + [
            float(results["out"][o["key"]][i]) for o in active_out
        ] for i in range(display_n)]
        raw_df = pd.DataFrame(raw_rows, columns=["#"] + [o["label"] for o in active_out])
        raw_df.to_excel(writer, sheet_name="Raw Samples (500)", index=False)

        # 3. Output Statistics
        stat_rows = []
        for o in active_out:
            s = o_stats[o["key"]]
            stat_rows.append([o["label"], o.get("unit", "—")] + [round(s[f], 6) for f in stat_cols])
        pd.DataFrame(stat_rows, columns=["Output", "Unit"] + stat_cols).to_excel(
            writer, sheet_name="Output Statistics", index=False)

        # 4. Input Statistics
        inp_rows = []
        for p in ALL_PARAMS:
            active = p["key"] in results["active_params"]
            s = compute_stats(results["inp"][p["key"]]) if active else {}
            inp_rows.append(
                [p["label"], p.get("unit", "—"), "Yes" if active else "No"] +
                [round(s.get(f, 0), 6) for f in stat_cols]
            )
        pd.DataFrame(inp_rows, columns=["Parameter", "Unit", "Active"] + stat_cols).to_excel(
            writer, sheet_name="Input Statistics", index=False)

        # 5. P10-P50-P90
        p_rows = []
        for o in active_out:
            s = o_stats[o["key"]]
            p_rows.append([o["label"], o.get("unit", "—"),
                           round(s["p10"], 5), round(s["p25"], 5), round(s["p50"], 5),
                           round(s["p75"], 5), round(s["p90"], 5),
                           round(s["p75"] - s["p25"], 5), round(s["p90"] - s["p10"], 5)])
        pd.DataFrame(p_rows, columns=["Output", "Unit", "P10", "P25", "P50", "P75", "P90", "IQR", "P10-P90 Range"]
                     ).to_excel(writer, sheet_name="P10-P50-P90 Summary", index=False)

        # 6. Histogram Data
        hist_rows = []
        for o in active_out:
            cum = 0
            for i, b in enumerate(results["o_hist"][o["key"]]):
                cum += b["pct"]
                hist_rows.append([o["label"], o.get("unit", "—"), i + 1,
                                  round(b["lo"], 5), round(b["hi"], 5),
                                  b["count"], round(b["pct"], 3), round(min(100, cum), 3)])
        pd.DataFrame(hist_rows, columns=["Output", "Unit", "Bin", "Lower", "Upper", "Count", "Freq%", "Cum%"]
                     ).to_excel(writer, sheet_name="Histogram Data", index=False)

        # 7. Sensitivity
        sen_rows = []
        for o in active_out:
            for i, d in enumerate(results["sensitivity"][o["key"]]):
                ab = abs(d["corr"])
                sen_rows.append([o["label"], i + 1, d["key"], round(d["corr"], 6), round(ab, 6),
                                  "Strong" if ab > 0.7 else "Moderate" if ab > 0.4 else "Weak" if ab > 0.2 else "Negligible"])
        pd.DataFrame(sen_rows, columns=["Output", "Rank", "Input", "Spearman rho", "Abs rho", "Strength"]
                     ).to_excel(writer, sheet_name="Sensitivity Analysis", index=False)

        # 8. Correlation Matrix
        if results["corr_data"]:
            keys = list(results["corr_data"].keys())
            mat = [[results["corr_data"][r].get(c, 0) for c in keys] for r in keys]
            pd.DataFrame(mat, index=keys, columns=keys).to_excel(writer, sheet_name="Correlation Matrix")

        # 9. RMR Classes
        if results["out_enabled"].get("RMR") and results["rmr_dist"]:
            cum = 0
            rmr_rows = []
            for cls, cnt in results["rmr_dist"].items():
                pct = round(cnt / n * 100, 3)
                cum += pct
                rmr_rows.append([f"Class {cls}", rmr_label(cls), cnt, pct, round(min(100, cum), 3)])
            pd.DataFrame(rmr_rows, columns=["Class", "Description", "Count", "Probability%", "Cumulative%"]
                         ).to_excel(writer, sheet_name="RMR Classification", index=False)

        # 10. ANN Results
        if results.get("ann"):
            a = results["ann"]
            summary = [
                ["Target Output", a["target_output"]],
                ["Train Samples", a["n_train"]], ["Test Samples", a["n_test"]],
                ["Test R²",  round(a["metrics"]["test_r2"], 6)],
                ["Test RMSE", round(a["metrics"]["test_rmse"], 6)],
                ["Test MAE",  round(a["metrics"]["test_mae"], 6)],
                ["Train R²",  round(a["metrics"]["train_r2"], 6)],
                ["Train RMSE", round(a["metrics"]["train_rmse"], 6)],
                ["Train MAE",  round(a["metrics"]["train_mae"], 6)],
            ]
            pd.DataFrame(summary, columns=["Metric", "Value"]).to_excel(
                writer, sheet_name="ANN Results", index=False)

        # 11. Reliability
        if results.get("reliability_data"):
            rd = results["reliability_data"]
            fd = results.get("form_data") or {}
            fs_stats = o_stats.get("FS_dist", {})
            rel_rows = [
                ["Method", "PoF", "Beta", "Interpretation"],
                ["Monte Carlo (MCS)", round(rd["PoF"] * 100, 5), round(rd["beta"], 5),
                 "High" if rd["beta"] > 3 else "Moderate" if rd["beta"] > 2 else "Low" if rd["beta"] > 1 else "Unreliable"],
                ["FORM (1st Order)", round(fd.get("PoF_form", 0) * 100, 5),
                 round(fd.get("beta_form", 0), 5), "Linearised LSF"],
            ]
            pd.DataFrame(rel_rows).to_excel(writer, sheet_name="Reliability Analysis", index=False, header=False)

    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def validate_param(key: str, val, field: str):
    if val in ("", None):
        return None
    try:
        n = float(val)
    except Exception:
        return {"level": "error", "msg": "Must be a number"}
    r = PARAM_RANGES.get(key)
    if not r or field not in ("mean", "mode"):
        return None
    if n < r["min"]:
        return {"level": "error", "msg": f"Below min {r['min']} {r['unit']} [{r['ref']}]"}
    if n > r["max"]:
        return {"level": "error", "msg": f"Above max {r['max']} {r['unit']} [{r['ref']}]"}
    if n < r["warnLo"] or n > r["warnHi"]:
        return {"level": "warning", "msg": f"Unusual: typical {r['warnLo']}–{r['warnHi']} {r['unit']}"}
    return {"level": "ok"}


def validate_all(params: dict, active_keys: set):
    errors, warnings = [], []
    for key in active_keys:
        cfg = params.get(key, {})
        for f in ["mean", "mode"]:
            val = cfg.get(f)
            v = validate_param(key, val, f)
            if v and v["level"] == "error":
                errors.append({"key": key, "field": f, "msg": v["msg"]})
            if v and v["level"] == "warning":
                warnings.append({"key": key, "field": f, "msg": v["msg"]})
    return errors, warnings


# ─────────────────────────────────────────────────────────────────────────────
# HISTOGRAM CHART (using st.bar_chart via pandas)
# ─────────────────────────────────────────────────────────────────────────────
def make_hist_df(hist_data: List[dict]) -> pd.DataFrame:
    if not hist_data:
        return pd.DataFrame()
    labels = [f"{b['lo']:.3f}" for b in hist_data]
    counts = [b["count"] for b in hist_data]
    return pd.DataFrame({"count": counts}, index=labels)


# ─────────────────────────────────────────────────────────────────────────────
# TORNADO CHART
# ─────────────────────────────────────────────────────────────────────────────
def make_tornado_df(items: List[dict]) -> pd.DataFrame:
    rows = items[:10]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame({
        "Parameter": [d["key"] for d in rows],
        "Spearman ρ": [round(d["corr"], 4) for d in rows],
    }).set_index("Parameter")


# ─────────────────────────────────────────────────────────────────────────────
# PARAM INPUT WIDGET
# ─────────────────────────────────────────────────────────────────────────────
def param_input_row(param: dict, cfg: dict, active: bool, key_prefix: str):
    """Render distribution inputs for one parameter inside an expander."""
    pk = param["key"]
    dist = cfg.get("dist", "Normal")
    fields = DIST_FIELDS.get(dist, ["mean"])

    col_dist, *rest = st.columns([2] + [1] * len(fields))
    with col_dist:
        new_dist = st.selectbox(
            "Distribution",
            DISTRIBUTIONS,
            index=DISTRIBUTIONS.index(dist),
            key=f"{key_prefix}_{pk}_dist",
            disabled=not active,
            label_visibility="collapsed",
        )
        if new_dist != dist:
            st.session_state.params[pk]["dist"] = new_dist
            st.rerun()

    new_fields = DIST_FIELDS.get(new_dist, ["mean"])
    for i, f in enumerate(new_fields):
        with rest[i] if i < len(rest) else st.container():
            val = cfg.get(f, "")
            new_val = st.text_input(
                f,
                value=str(val),
                key=f"{key_prefix}_{pk}_{f}",
                disabled=not active,
                placeholder="—" if not active else f,
                label_visibility="visible",
            )
            if new_val != str(val):
                st.session_state.params[pk][f] = new_val


# ─────────────────────────────────────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────────────────────────────────────
def main():
    init_session()

    # ── HEADER ──────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style='background:linear-gradient(90deg,#1a2230 0%,#0e1318 100%);
                padding:18px 24px;border-radius:10px;margin-bottom:20px;
                border-left:4px solid #e8a020;'>
        <span style='font-size:22px;font-weight:800;color:#e8a020;letter-spacing:2px;'>
        ⛰️  ROCK MASS VARIABILITY ANALYSIS</span>
        <span style='font-size:12px;color:#e8a020;font-weight:600;'> v{APP_VERSION}</span><br>
        <span style='font-size:11px;color:#607080;letter-spacing:1px;'>
        MONTE CARLO · RMR · Q-SYSTEM · HOEK-BROWN · MOHR-COULOMB ·
        SUPPORT PRESSURE · TUNNEL CCM · RELIABILITY · ANN · CORRELATED SAMPLING ·
        SPATIAL VARIABILITY · REGRESSION TOOLS</span>
    </div>
    """, unsafe_allow_html=True)

    # ── SIDEBAR — Simulation Controls ───────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Simulation Controls")

        st.session_state.project_name = st.text_input(
            "Project Name", value=st.session_state.project_name)

        st.session_state.iters = st.number_input(
            "Monte Carlo Iterations", min_value=10, max_value=100_000,
            value=st.session_state.iters, step=100)

        st.session_state.em_mode = st.radio(
            "Em Formula",
            ["HD", "SP"],
            index=0 if st.session_state.em_mode == "HD" else 1,
            format_func=lambda x: EM_MODES[x]["label"],
            help="\n".join([f"**{k}**: {v['note']}" for k, v in EM_MODES.items()]),
        )
        st.caption(f"_{EM_MODES[st.session_state.em_mode]['formula']}_")

        st.markdown("---")
        st.markdown("### 🏗️ Tunnel / Geotechnical Parameters")
        st.session_state.tunnel_diam = st.number_input(
            "Tunnel Diameter B (m)", min_value=1.0, max_value=30.0,
            value=st.session_state.tunnel_diam, step=0.5)
        st.session_state.tunnel_radius = st.number_input(
            "Tunnel Radius ri (m)", min_value=0.5, max_value=15.0,
            value=st.session_state.tunnel_radius, step=0.5)
        st.session_state.insitu_stress = st.number_input(
            "In-Situ Stress P₀ (MPa)", min_value=0.1, max_value=100.0,
            value=st.session_state.insitu_stress, step=0.5)
        st.session_state.applied_stress_ratio = st.slider(
            "Applied Stress Ratio", 0.01, 1.0,
            value=st.session_state.applied_stress_ratio, step=0.01)

        st.markdown("##### Convergence-Confinement Method")
        st.session_state.ccm_method = st.radio(
            "CCM Method", ["MC", "HB"],
            index=0 if st.session_state.ccm_method == "MC" else 1,
            format_func=lambda x: "Simplified (Mohr-Coulomb)" if x == "MC" else "Extended (Hoek-Brown)",
            help="**Simplified**: elastic-perfectly-plastic Mohr-Coulomb closed form "
                 "(Hoek, *Practical Rock Engineering*, Ch. 12, Eqs. 4–7).\n\n"
                 "**Extended**: Hoek-Brown based ground reaction curves fitted to the "
                 "rigorous elasto-plastic Hoek-Brown solution (Carranza-Torres & "
                 "Fairhurst 1999; Duncan Fama 1993; Hoek 2000). Intended for weak / "
                 "squeezing ground (σcm/p0 well below 1); for stronger ground the "
                 "simplified method remains broadly applicable.",
            horizontal=True,
        )
        if st.session_state.ccm_method == "HB":
            st.session_state.support_pressure_ratio = st.slider(
                "Support Pressure Ratio pᵢ/p₀", 0.0, 0.9,
                value=st.session_state.support_pressure_ratio, step=0.05,
                help="Ratio of internal support pressure to in-situ stress. "
                     "0 = unsupported tunnel (ground reaction curve at pᵢ = 0).")

        st.markdown("---")
        st.markdown("### 🔗 Correlated Input Sampling")
        st.session_state.corr_enabled = st.checkbox(
            "Enable correlated sampling (Iman-Conover)",
            value=st.session_state.corr_enabled,
            help="Imposes a target rank-correlation structure between input "
                 "parameters (e.g. UCS–GSI, Jr–Ja) via the Iman & Conover (1982) "
                 "method: a Cholesky decomposition of the target correlation matrix "
                 "generates correlated normal scores, which are used only to "
                 "re-order each parameter's independently-sampled values — so each "
                 "parameter's own marginal distribution is preserved exactly.")
        if st.session_state.corr_enabled:
            with st.expander("Set pairwise correlations", expanded=True):
                st.caption("Correlation coefficients (−1 to 1) between active input parameters. "
                           "Physically-motivated defaults are pre-filled for UCS–GSI and Jr–Ja.")
                act_now = get_active_params(st.session_state.out_enabled, st.session_state.em_mode)
                act_keys_now = [k for k in ALL_PARAM_KEYS if k in act_now]
                new_pairs = {}
                for i, a in enumerate(act_keys_now):
                    for b in act_keys_now[i + 1:]:
                        default_rho = st.session_state.corr_pairs.get(
                            (a, b), st.session_state.corr_pairs.get((b, a), 0.0))
                        if default_rho != 0.0 or (a, b) in DEFAULT_CORR_PAIRS or (b, a) in DEFAULT_CORR_PAIRS:
                            rho = st.slider(f"{a} ↔ {b}", -1.0, 1.0, value=float(default_rho),
                                            step=0.05, key=f"corr_{a}_{b}")
                            if abs(rho) > 1e-9:
                                new_pairs[(a, b)] = rho
                with st.popover("+ Add another pair"):
                    ca, cb = st.columns(2)
                    pa = ca.selectbox("Param A", act_keys_now, key="corr_add_a")
                    pb = cb.selectbox("Param B", act_keys_now, key="corr_add_b")
                    rho_new = st.slider("Correlation", -1.0, 1.0, 0.0, 0.05, key="corr_add_rho")
                    if st.button("Add / Update", key="corr_add_btn") and pa != pb and abs(rho_new) > 1e-9:
                        st.session_state.corr_pairs[(pa, pb)] = rho_new
                        st.rerun()
                st.session_state.corr_pairs.update(new_pairs)

        st.markdown("---")
        st.markdown("### 📤 Outputs to Compute")
        for grp_key, grp_label in OUTPUT_GROUPS.items():
            grp_outputs = [o for o in ALL_OUTPUTS if o["group"] == grp_key]
            with st.expander(grp_label, expanded=(grp_key == "core")):
                for o in grp_outputs:
                    st.session_state.out_enabled[o["key"]] = st.checkbox(
                        f"{o['label']} [{o.get('unit', '—')}]",
                        value=st.session_state.out_enabled.get(o["key"], o["group"] == "core"),
                        key=f"out_{o['key']}",
                    )

        st.markdown("---")
        # Project JSON export/import
        st.markdown("### 💾 Project")
        corr_pairs_serializable = {f"{a}|{b}": rho for (a, b), rho in st.session_state.corr_pairs.items()}
        proj_json = json.dumps({
            "version": APP_VERSION,
            "name": st.session_state.project_name,
            "params": st.session_state.params,
            "iters": st.session_state.iters,
            "out_enabled": st.session_state.out_enabled,
            "em_mode": st.session_state.em_mode,
            "ccm_method": st.session_state.ccm_method,
            "support_pressure_ratio": st.session_state.support_pressure_ratio,
            "corr_enabled": st.session_state.corr_enabled,
            "corr_pairs": corr_pairs_serializable,
            "tunnel_length": st.session_state.tunnel_length,
            "corr_length": st.session_state.corr_length,
            "segment_length": st.session_state.segment_length,
        }, indent=2)
        st.download_button("⬇ Download Project (.json)", data=proj_json,
                           file_name=f"{st.session_state.project_name.replace(' ','_')}.json",
                           mime="application/json")
        uploaded = st.file_uploader("⬆ Load Project (.json)", type=["json"], key="proj_upload")
        if uploaded:
            try:
                data = json.load(uploaded)
                st.session_state.params     = data.get("params", st.session_state.params)
                st.session_state.iters      = data.get("iters", 1000)
                st.session_state.out_enabled= data.get("out_enabled", _default_out_enabled())
                st.session_state.em_mode    = data.get("em_mode", "HD")
                st.session_state.project_name = data.get("name", "My Project")
                st.session_state.ccm_method = data.get("ccm_method", "MC")
                st.session_state.support_pressure_ratio = data.get("support_pressure_ratio", 0.0)
                st.session_state.corr_enabled = data.get("corr_enabled", False)
                loaded_pairs = data.get("corr_pairs", {})
                st.session_state.corr_pairs = {
                    tuple(k.split("|")): v for k, v in loaded_pairs.items()
                } if loaded_pairs else dict(DEFAULT_CORR_PAIRS)
                st.session_state.tunnel_length = data.get("tunnel_length", 500.0)
                st.session_state.corr_length = data.get("corr_length", 20.0)
                st.session_state.segment_length = data.get("segment_length", 5.0)
                st.success(f"Loaded: {data.get('name', 'project')}")
                st.rerun()
            except Exception as e:
                st.error(f"Could not load project: {e}")

    # ── ACTIVE PARAMS ────────────────────────────────────────────────────────
    active_params = get_active_params(st.session_state.out_enabled, st.session_state.em_mode)
    active_out    = [o for o in ALL_OUTPUTS if st.session_state.out_enabled.get(o["key"])]

    # ── TABS ─────────────────────────────────────────────────────────────────
    (tab_inputs, tab_results, tab_ann, tab_spatial,
     tab_regression, tab_monitoring) = st.tabs([
        "📋 Input Parameters", "📊 Results", "🤖 ANN Model",
        "🌐 Spatial Variability", "📐 Regression Tools",
        "📡 Construction Monitoring (Beta)",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — INPUTS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_inputs:
        # Validation banner
        errors, warnings = validate_all(st.session_state.params, active_params)
        if errors:
            err_txt = "\n".join([f"• **{e['key']}** ({e['field']}): {e['msg']}" for e in errors[:5]])
            st.error(f"❌ **{len(errors)} validation error(s) — simulation blocked**\n\n{err_txt}")
        if warnings:
            warn_txt = "\n".join([f"• **{w['key']}** ({w['field']}): {w['msg']}" for w in warnings[:3]])
            st.warning(f"⚠️ **{len(warnings)} warning(s)**\n\n{warn_txt}")

        st.markdown(
            f"> Active parameters: **{len(active_params)}** of {len(ALL_PARAMS)} · "
            f"Active outputs: **{len(active_out)}** of {len(ALL_OUTPUTS)} · "
            f"Em formula: **{EM_MODES[st.session_state.em_mode]['label']}**"
        )

        for grp in PARAM_GROUPS:
            st.markdown(f"#### {grp['label']}")
            for param in grp["params"]:
                pk = param["key"]
                active = pk in active_params
                cfg = st.session_state.params[pk]
                label = f"{'✅' if active else '⬜'} **{param['label']}**"
                if param.get("unit"):
                    label += f" `[{param['unit']}]`"
                label += f" — *{param['desc']}*"

                with st.expander(label, expanded=active):
                    if not active:
                        st.caption("*Not required by any enabled output. Enable an output that depends on this parameter.*")
                    param_input_row(param, cfg, active, "inp")
            st.divider()

        # RUN button
        col_run, col_info = st.columns([1, 3])
        with col_run:
            run_clicked = st.button("▶ RUN SIMULATION", type="primary",
                                    disabled=bool(errors), use_container_width=True)
        with col_info:
            if errors:
                st.error("Fix validation errors before running.")
            else:
                st.info(f"Ready: {st.session_state.iters:,} iterations · {len(active_out)} outputs")

        if run_clicked:
            # Fill check
            missing = []
            for p in ALL_PARAMS:
                if p["key"] not in active_params:
                    continue
                cfg = st.session_state.params[p["key"]]
                for f in DIST_FIELDS.get(cfg["dist"], ["mean"]):
                    if cfg.get(f) in ("", None):
                        missing.append(f"{p['label']} → '{f}'")
            if missing:
                st.error("Please fill in all required fields:\n" + "\n".join(f"• {m}" for m in missing[:8]))
            else:
                with st.spinner(f"Running {st.session_state.iters:,} Monte Carlo iterations…"):
                    try:
                        results = run_simulation(
                            params=st.session_state.params,
                            iters=st.session_state.iters,
                            out_enabled=st.session_state.out_enabled,
                            em_mode=st.session_state.em_mode,
                            tunnel_diam=st.session_state.tunnel_diam,
                            tunnel_radius=st.session_state.tunnel_radius,
                            insitu_stress=st.session_state.insitu_stress,
                            applied_stress_ratio=st.session_state.applied_stress_ratio,
                            corr_enabled=st.session_state.corr_enabled,
                            corr_pairs=st.session_state.corr_pairs,
                            ccm_method=st.session_state.ccm_method,
                            support_pressure_ratio=st.session_state.support_pressure_ratio,
                        )
                        st.session_state.results = results
                        st.success(f"✅ Simulation complete — {results['n']:,} iterations · {len(active_out)} outputs computed")
                    except Exception as e:
                        st.error(f"Simulation error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — RESULTS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_results:
        results = st.session_state.results
        if results is None:
            st.info("No results yet. Configure inputs and click **Run Simulation**.")
        else:
            res_active_out = [o for o in ALL_OUTPUTS if results["out_enabled"].get(o["key"])]

            # Excel export
            col_ex1, col_ex2 = st.columns([1, 4])
            with col_ex1:
                try:
                    xlsx_bytes = export_excel(results, res_active_out, st.session_state.project_name)
                    st.download_button(
                        "⬇ Export Excel (.xlsx)",
                        data=xlsx_bytes,
                        file_name=f"{st.session_state.project_name.replace(' ','_')}_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                except Exception as e:
                    st.warning(f"Excel export error: {e}")
            with col_ex2:
                st.caption(f"Last run: {results['n']:,} iterations · Em: {EM_MODES[results['em_mode']]['label']} · {len(res_active_out)} outputs")

            # Sub-tabs
            sub = st.tabs(["📈 Statistics", "📉 Histograms", "🌪 Sensitivity",
                           "🔗 Correlation", "🏷 RMR Classes", "🛡 Reliability",
                           "📋 Raw Samples"])

            # ── Sub-tab: Statistics ──────────────────────────────────────────
            with sub[0]:
                st.markdown("#### Output Statistics")
                stat_fields = ["mean", "std", "min", "p10", "p25", "p50", "p75", "p90", "p95", "max"]
                stat_rows = []
                for o in res_active_out:
                    s = results["o_stats"][o["key"]]
                    stat_rows.append({
                        "Output": o["label"],
                        "Unit": o.get("unit", "—"),
                        **{f.upper(): round(s[f], 4) for f in stat_fields},
                    })
                st.dataframe(pd.DataFrame(stat_rows), use_container_width=True)

                st.markdown("#### P10 / P50 / P90 Summary")
                pct_rows = []
                for o in res_active_out:
                    s = results["o_stats"][o["key"]]
                    pct_rows.append({
                        "Output": o["label"],
                        "Unit": o.get("unit", "—"),
                        "P10": round(s["p10"], 4),
                        "P25": round(s["p25"], 4),
                        "P50 (Median)": round(s["p50"], 4),
                        "P75": round(s["p75"], 4),
                        "P90": round(s["p90"], 4),
                        "IQR (P75-P25)": round(s["p75"] - s["p25"], 4),
                    })
                st.dataframe(pd.DataFrame(pct_rows), use_container_width=True)

            # ── Sub-tab: Histograms ──────────────────────────────────────────
            with sub[1]:
                h_col1, h_col2 = st.columns(2)
                with h_col1:
                    st.markdown("**Input Distribution**")
                    inp_param_options = [p for p in ALL_PARAMS if p["key"] in results["active_params"]]
                    if inp_param_options:
                        sel_inp = st.selectbox("Select Input Parameter",
                                               [p["label"] for p in inp_param_options],
                                               key="sel_inp_hist")
                        sel_inp_key = inp_param_options[[p["label"] for p in inp_param_options].index(sel_inp)]["key"]
                        hist_df = make_hist_df(results["i_hist"][sel_inp_key])
                        if not hist_df.empty:
                            st.bar_chart(hist_df, color="#30b8c0")
                            s = compute_stats(results["inp"][sel_inp_key])
                            for k in ["mean", "std", "min", "p10", "p50", "p90", "max"]:
                                c1, c2 = st.columns(2)
                                c1.caption(k.upper())
                                c2.caption(f"**{s[k]:.4f}**")

                with h_col2:
                    st.markdown("**Output Distribution**")
                    if res_active_out:
                        sel_out = st.selectbox("Select Output",
                                               [o["label"] for o in res_active_out],
                                               key="sel_out_hist")
                        sel_out_key = res_active_out[[o["label"] for o in res_active_out].index(sel_out)]["key"]
                        out_hist_df = make_hist_df(results["o_hist"][sel_out_key])
                        if not out_hist_df.empty:
                            st.bar_chart(out_hist_df, color="#e8a020")
                            s = results["o_stats"][sel_out_key]
                            for k in ["mean", "std", "min", "p10", "p50", "p90", "p95", "max"]:
                                c1, c2 = st.columns(2)
                                c1.caption(k.upper())
                                c2.caption(f"**{s[k]:.4f}**")

            # ── Sub-tab: Sensitivity ─────────────────────────────────────────
            with sub[2]:
                if res_active_out:
                    sel_out_sens = st.selectbox("Select Output for Sensitivity",
                                                [o["label"] for o in res_active_out],
                                                key="sel_sens_out")
                    sel_out_key_s = res_active_out[
                        [o["label"] for o in res_active_out].index(sel_out_sens)
                    ]["key"]
                    items = results["sensitivity"][sel_out_key_s][:10]
                    if items:
                        tornado_df = make_tornado_df(items)
                        st.bar_chart(tornado_df, color="#4090e8")

                        st.markdown("**Spearman Rank Correlation Table**")
                        t_rows = []
                        for i, d in enumerate(items):
                            ab = abs(d["corr"])
                            t_rows.append({
                                "Rank": i + 1,
                                "Parameter": d["key"],
                                "ρ": round(d["corr"], 4),
                                "|ρ|": round(ab, 4),
                                "Strength": "Strong" if ab > 0.7 else "Moderate" if ab > 0.4 else "Weak" if ab > 0.2 else "Negligible",
                            })
                        st.dataframe(pd.DataFrame(t_rows), use_container_width=True)

                        # All outputs tornado summary
                        st.markdown("---")
                        st.markdown("**All Outputs — Top Influencing Parameter**")
                        summary_rows = []
                        for o in res_active_out:
                            top = results["sensitivity"][o["key"]]
                            if top:
                                t = top[0]
                                summary_rows.append({
                                    "Output": o["label"],
                                    "Top Influence": t["key"],
                                    "ρ": round(t["corr"], 4),
                                    "Direction": "Positive" if t["corr"] >= 0 else "Negative",
                                })
                        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

            # ── Sub-tab: Correlation ─────────────────────────────────────────
            with sub[3]:
                if results["corr_data"]:
                    keys = list(results["corr_data"].keys())
                    mat  = np.array([[results["corr_data"][r].get(c, 0) for c in keys] for r in keys])
                    corr_df = pd.DataFrame(mat, index=keys, columns=keys).round(3)
                    st.dataframe(corr_df.style.background_gradient(cmap="RdBu_r", vmin=-1, vmax=1),
                                 use_container_width=True)
                else:
                    st.info("Not enough active parameters to compute correlation matrix.")

            # ── Sub-tab: RMR Classes ─────────────────────────────────────────
            with sub[4]:
                if results["out_enabled"].get("RMR") and results["rmr_dist"]:
                    rmr_rows = []
                    cum = 0
                    for cls, cnt in results["rmr_dist"].items():
                        pct = cnt / results["n"] * 100
                        cum += pct
                        rmr_rows.append({
                            "Class": f"Class {cls}",
                            "Description": rmr_label(cls),
                            "Count": cnt,
                            "Probability %": round(pct, 2),
                            "Cumulative %": round(min(100, cum), 2),
                        })
                    st.dataframe(pd.DataFrame(rmr_rows), use_container_width=True)

                    # Bar chart
                    rmr_chart = pd.DataFrame({
                        "Probability %": [r["Probability %"] for r in rmr_rows]
                    }, index=[r["Class"] for r in rmr_rows])
                    st.bar_chart(rmr_chart, color="#34c070")
                else:
                    st.info("Enable RMR output to see classification breakdown.")

            # ── Sub-tab: Reliability ─────────────────────────────────────────
            with sub[5]:
                rd = results.get("reliability_data")
                fd = results.get("form_data")
                if rd is None:
                    st.info("Enable **Factor of Safety (FS)** output to run reliability analysis.")
                else:
                    rel_cat = ("High Reliability" if rd["beta"] > 3 else
                               "Moderate Reliability" if rd["beta"] > 2 else
                               "Low Reliability" if rd["beta"] > 1 else "Unreliable")

                    c1, c2, c3 = st.columns(3)
                    c1.metric("PoF (Monte Carlo)", f"{rd['PoF']*100:.3f}%")
                    c2.metric("β (Cornell)",       f"{rd['beta']:.3f}")
                    c3.metric("Classification",    rel_cat)

                    if fd:
                        c4, c5 = st.columns(2)
                        c4.metric("PoF (FORM)",  f"{fd['PoF_form']*100:.3f}%")
                        c5.metric("β (FORM)",    f"{fd['beta_form']:.3f}")

                    fs_stats = results["o_stats"].get("FS_dist", {})
                    st.markdown("**Factor of Safety Distribution**")
                    cols_fs = st.columns(4)
                    for i, (lbl, val) in enumerate([
                        ("Mean FS", fs_stats.get("mean", 0)),
                        ("Std Dev", fs_stats.get("std", 0)),
                        ("P50",     fs_stats.get("p50", 0)),
                        ("P90",     fs_stats.get("p90", 0)),
                    ]):
                        cols_fs[i].metric(lbl, f"{val:.4f}")

                    fs_hist = make_hist_df(results["o_hist"].get("FS_dist", []))
                    if not fs_hist.empty:
                        st.bar_chart(fs_hist, color="#70e8a0")

                    st.markdown("---")
                    st.markdown("**Reliability Benchmarks**")
                    benchmarks = [
                        ("β ≥ 4.75", "≈ 10⁻⁶",  "Nuclear / critical safety"),
                        ("β ≥ 3.50", "≈ 0.023%", "High consequence (dams)"),
                        ("β ≥ 3.00", "≈ 0.13%",  "Tunnels / piles"),
                        ("β ≥ 2.50", "≈ 0.62%",  "Geotechnical nominal"),
                        ("β ≥ 2.00", "≈ 2.3%",   "Low consequence"),
                    ]
                    bm_df = pd.DataFrame(benchmarks, columns=["β Threshold", "PoF", "Application"])
                    bm_df["Met?"] = bm_df["β Threshold"].apply(
                        lambda x: "✅" if rd["beta"] >= float(x.split("≥")[1].strip()) else "❌")
                    st.dataframe(bm_df, use_container_width=True)

            # ── Sub-tab: Raw Samples ─────────────────────────────────────────
            with sub[6]:
                display_n = min(500, results["n"])
                st.caption(f"Showing first {display_n:,} of {results['n']:,} iterations")
                raw_data = {"#": list(range(1, display_n + 1))}
                for o in res_active_out:
                    arr = results["out"][o["key"]]
                    raw_data[o["label"]] = [round(float(arr[i]), 5) for i in range(display_n)]
                if results["out_enabled"].get("RMR"):
                    rmr_arr = results["out"]["RMR"]
                    raw_data["RMR Class"] = [
                        f"{rmr_class(rmr_arr[i])} — {rmr_label(rmr_class(rmr_arr[i]))}"
                        for i in range(display_n)
                    ]
                st.dataframe(pd.DataFrame(raw_data), use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — ANN
    # ══════════════════════════════════════════════════════════════════════════
    with tab_ann:
        results = st.session_state.results
        if results is None:
            st.info("Run simulation first to enable ANN training.")
        else:
            res_active_out = [o for o in ALL_OUTPUTS if results["out_enabled"].get(o["key"])]
            st.markdown("### 🤖 Artificial Neural Network — Predictive Model")
            st.markdown(
                "Train a feedforward ANN on simulation outputs to learn the mapping from "
                "input rock mass parameters to a target output. Uses ReLU activations, "
                "He initialisation, and mini-batch SGD."
            )

            col_a, col_b = st.columns(2)
            with col_a:
                st.session_state.ann_target = st.selectbox(
                    "Target Output",
                    [o["key"] for o in res_active_out],
                    format_func=lambda k: next((o["label"] for o in ALL_OUTPUTS if o["key"] == k), k),
                )
                st.session_state.ann_split  = st.slider("Train/Test Split (%)", 50, 95,
                                                          st.session_state.ann_split)
                st.session_state.ann_epochs = st.number_input("Epochs", 10, 2000,
                                                               st.session_state.ann_epochs)
                st.session_state.ann_lr     = st.number_input("Learning Rate", 0.0001, 0.5,
                                                               st.session_state.ann_lr, format="%.4f")
            with col_b:
                st.session_state.ann_hidden  = st.number_input("Hidden Layers", 1, 5,
                                                                 st.session_state.ann_hidden)
                st.session_state.ann_neurons = st.number_input("Neurons per Layer", 4, 128,
                                                                 st.session_state.ann_neurons)
                st.session_state.ann_batch   = st.number_input("Batch Size", 8, 256,
                                                                 st.session_state.ann_batch)

            if st.button("🚀 Train ANN", type="primary"):
                target_key = st.session_state.ann_target
                target_arr = results["out"][target_key]
                apk = results["active_params"]
                n   = results["n"]

                if n < 20:
                    st.error("Need at least 20 simulation samples.")
                else:
                    X = np.column_stack([results["inp"][k] for k in apk])
                    Y = target_arr.reshape(-1, 1)

                    # Normalise
                    Xn, Xmins, Xmaxs = norm_data(X)
                    Yn, Ymins, Ymaxs  = norm_data(Y)

                    # Split
                    idx   = np.random.permutation(n)
                    split = int(n * st.session_state.ann_split / 100)
                    tr_idx, te_idx = idx[:split], idx[split:]

                    Xtr, Ytr = Xn[tr_idx], Yn[tr_idx]
                    Xte, Yte = Xn[te_idx], Yn[te_idx]

                    # Architecture
                    sizes = [len(apk)] + [st.session_state.ann_neurons] * st.session_state.ann_hidden + [1]
                    net   = NeuralNetwork(sizes)

                    prog_bar = st.progress(0, text="Training…")
                    t_losses, v_losses = [], []
                    epochs = st.session_state.ann_epochs
                    batch  = st.session_state.ann_batch
                    lr     = st.session_state.ann_lr

                    for ep in range(epochs):
                        # Shuffle
                        perm = np.random.permutation(len(Xtr))
                        ep_loss = 0.0
                        for b_start in range(0, len(Xtr), batch):
                            b_idx = perm[b_start:b_start + batch]
                            ep_loss += net.train_step(Xtr[b_idx], Ytr[b_idx], lr)
                        ep_loss /= max(1, len(Xtr) // batch)
                        t_losses.append(ep_loss)

                        pred_v = net.predict_batch(Xte)
                        v_loss = float(np.mean((pred_v - Yte) ** 2))
                        v_losses.append(v_loss)

                        prog_bar.progress((ep + 1) / epochs,
                                          text=f"Epoch {ep+1}/{epochs} | Train: {ep_loss:.5f} | Val: {v_loss:.5f}")

                    prog_bar.empty()

                    # Evaluate
                    pred_te = net.predict_batch(Xte)
                    pred_tr = net.predict_batch(Xtr)
                    Yscale  = Ymaxs[0] - Ymins[0] if Ymaxs[0] > Ymins[0] else 1

                    te_actual = target_arr[te_idx]
                    te_pred   = (pred_te.ravel() * Yscale) + Ymins[0]
                    tr_actual = target_arr[tr_idx]
                    tr_pred   = (pred_tr.ravel() * Yscale) + Ymins[0]

                    metrics = {
                        "test_r2":    r2_score(te_actual, te_pred),
                        "test_rmse":  rmse_score(te_actual, te_pred),
                        "test_mae":   mae_score(te_actual, te_pred),
                        "train_r2":   r2_score(tr_actual, tr_pred),
                        "train_rmse": rmse_score(tr_actual, tr_pred),
                        "train_mae":  mae_score(tr_actual, tr_pred),
                    }

                    ann_result = {
                        "target_output": target_key,
                        "n_train": len(tr_idx),
                        "n_test":  len(te_idx),
                        "t_losses": t_losses,
                        "v_losses": v_losses,
                        "te_actual": te_actual.tolist(),
                        "te_pred":   te_pred.tolist(),
                        "tr_actual": tr_actual.tolist(),
                        "tr_pred":   tr_pred.tolist(),
                        "metrics":   metrics,
                        "layer_sizes": sizes,
                    }
                    st.session_state.results["ann"] = ann_result
                    st.success("✅ ANN training complete!")

            # Show ANN results if available
            if results.get("ann"):
                ann = results["ann"]
                st.markdown("---")
                st.markdown("#### Training Results")

                c1, c2, c3, c4, c5, c6 = st.columns(6)
                m = ann["metrics"]
                c1.metric("Test R²",    f"{m['test_r2']:.4f}",  help="Closer to 1 is better")
                c2.metric("Test RMSE",  f"{m['test_rmse']:.4f}")
                c3.metric("Test MAE",   f"{m['test_mae']:.4f}")
                c4.metric("Train R²",   f"{m['train_r2']:.4f}")
                c5.metric("Train RMSE", f"{m['train_rmse']:.4f}")
                c6.metric("Train MAE",  f"{m['train_mae']:.4f}")

                # Loss curves
                loss_df = pd.DataFrame({
                    "Train Loss": ann["t_losses"],
                    "Val Loss":   ann["v_losses"],
                })
                st.markdown("**Loss Curve**")
                st.line_chart(loss_df)

                # Actual vs Predicted
                st.markdown("**Actual vs Predicted (Test Set, first 200)**")
                disp_n = min(200, len(ann["te_actual"]))
                ap_df  = pd.DataFrame({
                    "Actual":    ann["te_actual"][:disp_n],
                    "Predicted": ann["te_pred"][:disp_n],
                })
                st.line_chart(ap_df)

                st.markdown("**Test Set Sample Predictions**")
                pred_rows = []
                for i in range(min(50, len(ann["te_actual"]))):
                    act  = ann["te_actual"][i]
                    pred = ann["te_pred"][i]
                    err  = act - pred
                    pct  = abs(err / act * 100) if act != 0 else 0
                    pred_rows.append({
                        "#":        i + 1,
                        "Actual":   round(act, 5),
                        "Predicted":round(pred, 5),
                        "Error":    round(err, 5),
                        "Abs Err%": round(pct, 3),
                        "Quality":  "Excellent" if pct < 5 else "Good" if pct < 10 else "Fair" if pct < 20 else "Poor",
                    })
                st.dataframe(pd.DataFrame(pred_rows), use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB — SPATIAL VARIABILITY / RANDOM FIELDS (v2.0)
    # ══════════════════════════════════════════════════════════════════════════
    with tab_spatial:
        st.markdown("#### 🌐 Spatial Variability Along the Tunnel Alignment")
        st.caption(
            "A Monte Carlo run treats each iteration as an independent point realisation. "
            "A real tunnel encounters *spatially correlated* rock conditions along its "
            "length — the point distribution alone cannot say how likely a given stretch "
            "is to hit poor ground. This module generates a 1-D random field of a chosen "
            "rock mass property along the tunnel alignment, using an exponential "
            "(Markov) autocorrelation function discretised via Cholesky decomposition, "
            "following the random-field methodology summarised by Wang & Cao (2014), and "
            "reports spatial-averaging effects via Vanmarcke's (1977) variance reduction "
            "function."
        )

        spatial_options = ["RMR", "Q", "GSI", "Rms"]
        spatial_bounds = {"RMR": (0, 100), "Q": (0.001, None), "GSI": (0, 100), "Rms": (0, None)}
        spatial_bad_dir = {"RMR": "below", "Q": "below", "GSI": "below", "Rms": "below"}

        c1, c2, c3 = st.columns(3)
        with c1:
            st.session_state.tunnel_length = st.number_input(
                "Tunnel Length (m)", min_value=10.0, max_value=20000.0,
                value=st.session_state.tunnel_length, step=10.0)
            st.session_state.segment_length = st.number_input(
                "Segment / Discretisation Length (m)", min_value=0.5, max_value=100.0,
                value=st.session_state.segment_length, step=0.5)
        with c2:
            st.session_state.corr_length = st.number_input(
                "Scale of Fluctuation θ (m)", min_value=0.5, max_value=2000.0,
                value=st.session_state.corr_length, step=1.0,
                help="Distance over which the rock mass property remains correlated. "
                     "Typical values in the literature range from a few metres (highly "
                     "variable jointed rock) to tens of metres (more homogeneous masses).")
            st.session_state.spatial_n_real = st.number_input(
                "Number of Field Realisations", min_value=20, max_value=5000,
                value=st.session_state.spatial_n_real, step=20)
        with c3:
            st.session_state.spatial_param = st.selectbox(
                "Property to Model Spatially", spatial_options,
                index=spatial_options.index(st.session_state.spatial_param))
            support_spacing = st.number_input(
                "Support / Panel Spacing (m)", min_value=0.5, max_value=100.0,
                value=min(5.0, st.session_state.segment_length * 4), step=0.5,
                help="Window length used to assess the probability that a single "
                     "support panel / round encounters poor ground.")

        sp_key = st.session_state.spatial_param
        results_for_stats = st.session_state.results
        have_mc_stats = (results_for_stats is not None and
                          results_for_stats["out_enabled"].get(sp_key) and
                          sp_key in results_for_stats["o_stats"])

        use_mc = False
        if have_mc_stats:
            use_mc = st.checkbox(
                f"Use mean/std of {sp_key} from the last Monte Carlo run "
                f"(mean={results_for_stats['o_stats'][sp_key]['mean']:.2f}, "
                f"std={results_for_stats['o_stats'][sp_key]['std']:.2f})",
                value=True)

        if use_mc:
            field_mean = results_for_stats["o_stats"][sp_key]["mean"]
            field_std = results_for_stats["o_stats"][sp_key]["std"]
        else:
            cm1, cm2 = st.columns(2)
            field_mean = cm1.number_input(f"Mean {sp_key}", value=50.0 if sp_key in ("RMR", "GSI") else 5.0)
            field_std = cm2.number_input(f"Std Dev {sp_key}", value=10.0 if sp_key in ("RMR", "GSI") else 2.0, min_value=0.01)

        default_thr = {"RMR": 41.0, "Q": 1.0, "GSI": 25.0, "Rms": max(field_mean * 0.3, 0.1)}
        threshold = st.number_input(
            f"'Poor Ground' Threshold for {sp_key} "
            f"({'below this = poor' if spatial_bad_dir[sp_key] == 'below' else 'above this = poor'})",
            value=float(default_thr[sp_key]))

        if st.button("▶ Generate Random Field", type="primary"):
            lo, hi = spatial_bounds[sp_key]
            field = generate_random_field(
                mean=field_mean, std=field_std, corr_length=st.session_state.corr_length,
                tunnel_length=st.session_state.tunnel_length,
                segment_length=st.session_state.segment_length,
                n_realizations=int(st.session_state.spatial_n_real), lo=lo, hi=hi)
            st.session_state.spatial_results = {
                "field": field, "param": sp_key, "threshold": threshold,
                "bad_dir": spatial_bad_dir[sp_key], "segment_length": st.session_state.segment_length,
                "tunnel_length": st.session_state.tunnel_length, "corr_length": st.session_state.corr_length,
                "support_spacing": support_spacing, "field_mean": field_mean, "field_std": field_std,
            }
            st.success(f"Generated {field.shape[0]:,} realisations × {field.shape[1]:,} segments.")

        sr = st.session_state.spatial_results
        if sr and sr["param"] == sp_key:
            field = sr["field"]
            n_real, n_seg = field.shape
            x = np.arange(n_seg) * sr["segment_length"]
            bad = field < sr["threshold"] if sr["bad_dir"] == "below" else field > sr["threshold"]

            st.markdown("##### Example Field Realisations")
            n_show = min(6, n_real)
            plot_df = pd.DataFrame({f"Realisation {i+1}": field[i] for i in range(n_show)}, index=x)
            plot_df.index.name = "Chainage (m)"
            st.line_chart(plot_df)

            # Probability any point along the whole tunnel is in poor ground
            prob_any_point = float(bad.mean())
            # Probability that a given realisation encounters at least one poor segment anywhere
            prob_any_realisation_hits_poor = float(np.any(bad, axis=1).mean())
            # Rolling-window (support-spacing) worst-case check
            win_segs = max(1, int(round(sr["support_spacing"] / sr["segment_length"])))
            if win_segs < n_seg:
                if sr["bad_dir"] == "below":
                    roll_worst = pd.DataFrame(field.T).rolling(win_segs).min().to_numpy().T
                    window_bad = roll_worst < sr["threshold"]
                else:
                    roll_worst = pd.DataFrame(field.T).rolling(win_segs).max().to_numpy().T
                    window_bad = roll_worst > sr["threshold"]
                window_bad = window_bad[:, win_segs - 1:]
                prob_window_hits_poor = float(window_bad.mean())
            else:
                prob_window_hits_poor = prob_any_realisation_hits_poor

            gamma = variance_reduction_gamma(sr["support_spacing"], sr["corr_length"])
            reduced_std = sr["field_std"] * math.sqrt(gamma)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("P(point in poor ground)", f"{prob_any_point*100:.1f}%")
            m2.metric(f"P(any {sr['support_spacing']:.0f} m panel poor)", f"{prob_window_hits_poor*100:.1f}%")
            m3.metric("P(tunnel hits poor ground at all)", f"{prob_any_realisation_hits_poor*100:.1f}%")
            m4.metric("Vanmarcke Γ (spatial averaging)", f"{gamma:.3f}")

            st.caption(
                f"Spatially averaging {sp_key} over a {sr['support_spacing']:.1f} m window reduces the "
                f"standard deviation from {sr['field_std']:.2f} to {reduced_std:.2f} "
                f"(variance reduction factor Γ = {gamma:.3f}, Vanmarcke 1977). This is why a spatial-average "
                "assessment over a support panel is less volatile than the point Monte Carlo distribution alone."
            )

            st.markdown("##### Distribution of Worst Segment per Realisation")
            worst_per_real = field.min(axis=1) if sr["bad_dir"] == "below" else field.max(axis=1)
            hist_df = pd.DataFrame({f"Worst {sp_key} per Realisation": worst_per_real})
            st.bar_chart(np.histogram(worst_per_real, bins=20)[0])

            # Store the mean field as a convenient series for the Regression Tools AR model
            st.session_state.spatial_results["mean_field_series"] = field.mean(axis=0).tolist()
        else:
            st.info("Set parameters above and click **Generate Random Field** to begin.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB — REGRESSION TOOLS (v2.0) — "Other Machine Learning Outputs"
    # ══════════════════════════════════════════════════════════════════════════
    with tab_regression:
        st.markdown("#### 📐 Linear & Auto-Regression Tools")
        st.caption(
            "Site-specific formulas linking an output to the correlated input parameters, "
            "for continuous use in the field once the dependent input parameters are known, "
            "without re-running the full simulator."
        )

        reg_sub = st.tabs(["Linear Regression", "Auto-Regression (spatial series)"])

        # ── Linear Regression ──
        with reg_sub[0]:
            results = st.session_state.results
            if results is None:
                st.info("Run a Monte Carlo simulation first (Input Parameters tab) to fit a regression model.")
            else:
                res_active_out = [o for o in ALL_OUTPUTS if results["out_enabled"].get(o["key"])]
                res_active_params = [k for k in ALL_PARAM_KEYS if k in results["active_params"]]
                if not res_active_out or len(res_active_params) < 1:
                    st.warning("Need at least one enabled output and one active input parameter.")
                else:
                    target_key = st.selectbox(
                        "Target Output", [o["key"] for o in res_active_out],
                        format_func=lambda k: next(o["label"] for o in ALL_OUTPUTS if o["key"] == k),
                        key="reg_target_select")
                    feature_keys = st.multiselect(
                        "Input Parameters (regressors)", res_active_params,
                        default=res_active_params, key="reg_features_select")

                    if st.button("Fit Linear Regression", type="primary") and feature_keys:
                        X = np.column_stack([results["inp"][k] for k in feature_keys])
                        y = results["out"][target_key]
                        st.session_state.reg_result = fit_linear_regression(X, y, feature_keys)
                        st.session_state.reg_result["target"] = target_key

                    rr = st.session_state.reg_result
                    if rr:
                        st.markdown("##### Fitted Formula")
                        st.code(rr["formula"], language="text")
                        m1, m2, m3 = st.columns(3)
                        m1.metric("R²", f"{rr['r2']:.4f}")
                        m2.metric("RMSE", f"{rr['rmse']:.4f}")
                        m3.metric("MAE", f"{rr['mae']:.4f}")
                        coef_df = pd.DataFrame(
                            [{"Parameter": k, "Coefficient": v} for k, v in rr["coefficients"].items()]
                            + [{"Parameter": "(Intercept)", "Coefficient": rr["intercept"]}])
                        st.dataframe(coef_df, use_container_width=True)
                        disp_n = min(300, len(rr["actual"]))
                        st.line_chart(pd.DataFrame({
                            "Actual": rr["actual"][:disp_n], "Predicted": rr["predicted"][:disp_n]}))

        # ── Auto-Regression ──
        with reg_sub[1]:
            sr = st.session_state.spatial_results
            if not sr or "mean_field_series" not in sr:
                st.info("Generate a spatial field first (Spatial Variability tab) to fit an AR model "
                        "on the along-tunnel series.")
            else:
                st.caption(
                    f"Fitting an AR(p) model to the mean {sr['param']} field over tunnel chainage, "
                    "via the Yule-Walker equations, so future segment values can be estimated from "
                    "recently observed ones as excavation advances.")
                st.session_state.ar_order = st.slider("AR Order (p)", 1, 10, value=st.session_state.ar_order)
                if st.button("Fit Auto-Regression Model", type="primary"):
                    st.session_state.ar_result = fit_yule_walker_ar(
                        np.array(sr["mean_field_series"]), order=st.session_state.ar_order)
                ar = st.session_state.ar_result
                if ar:
                    st.markdown("##### Fitted Formula")
                    st.code(ar["formula"], language="text")
                    m1, m2 = st.columns(2)
                    m1.metric("In-sample R²", f"{ar['r2']:.4f}")
                    m2.metric("AR Order", ar["order"])
                    st.dataframe(pd.DataFrame(
                        [{"Lag": i + 1, "Coefficient (φ)": c} for i, c in enumerate(ar["phi"])]),
                        use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB — CONSTRUCTION MONITORING (BETA) (v2.0)
    # ══════════════════════════════════════════════════════════════════════════
    with tab_monitoring:
        st.markdown("#### 📡 Real-Time Construction Monitoring — Beta / Prototype")
        st.warning(
            "**Scope note:** genuine real-time monitoring requires a live connection to a digital "
            "face-mapping / instrumentation system and an automated pipeline that continuously retrains "
            "the ANN surrogate as new data arrives — infrastructure this desktop app does not have access "
            "to. This tab instead prototypes the underlying *workflow*: as periodic face-mapping "
            "observations accumulate, they progressively narrow the input distributions and update the "
            "computed Q / RMR / support outputs, in the same way a live pipeline would — just applied here "
            "to an uploaded batch of observations rather than a streaming feed."
        )

        up_csv = st.file_uploader(
            "Upload face-mapping observations (.csv) — columns matching parameter keys "
            f"({', '.join(ALL_PARAM_KEYS)}), one row per mapped face/round", type=["csv"], key="mon_upload")

        if up_csv is not None:
            try:
                df_mon = pd.read_csv(up_csv)
                st.session_state.monitoring_data = df_mon
            except Exception as e:
                st.error(f"Could not read CSV: {e}")

        df_mon = st.session_state.monitoring_data
        if df_mon is None:
            st.info("Upload a CSV of periodic face-mapping observations to begin.")
        else:
            present_keys = [k for k in ALL_PARAM_KEYS if k in df_mon.columns]
            if not present_keys:
                st.error(f"No recognised parameter columns found. Expected some of: {', '.join(ALL_PARAM_KEYS)}")
            else:
                st.dataframe(df_mon.head(20), use_container_width=True)
                n_obs_total = len(df_mon)
                n_obs = st.slider(
                    "Observations received so far (simulating progressive data arrival)",
                    1, n_obs_total, value=n_obs_total)
                prior_pseudo_n = st.slider(
                    "Prior confidence (equivalent pseudo-observations)", 1, 50, value=5,
                    help="Higher values mean the original expert-defined distribution shrinks more "
                         "slowly as field data accumulates.")

                st.markdown("##### Updated Distributions (prior → data-informed)")
                update_rows = []
                updated_params = dict(st.session_state.params)
                subset = df_mon[present_keys].head(n_obs)
                for key in present_keys:
                    prior_cfg = st.session_state.params.get(key, _default_param_cfg())
                    try:
                        prior_mean = float(prior_cfg.get("mean") or 0)
                        prior_std  = float(prior_cfg.get("std") or max(abs(prior_mean) * 0.1, 1))
                    except (TypeError, ValueError):
                        prior_mean, prior_std = 0.0, 1.0
                    data_vals = subset[key].dropna().to_numpy(dtype=float)
                    if len(data_vals) == 0:
                        continue
                    data_mean = float(data_vals.mean())
                    data_std = float(data_vals.std()) if len(data_vals) > 1 else prior_std
                    n0 = prior_pseudo_n
                    n1 = len(data_vals)
                    updated_mean = (n0 * prior_mean + n1 * data_mean) / (n0 + n1)
                    updated_std = math.sqrt(
                        (n0 * prior_std ** 2 + n1 * data_std ** 2) / (n0 + n1)) / math.sqrt(1 + n1 / n0)
                    update_rows.append({
                        "Parameter": key, "Prior Mean": round(prior_mean, 3), "Prior Std": round(prior_std, 3),
                        "Data Mean (n={})".format(n1): round(data_mean, 3),
                        "Updated Mean": round(updated_mean, 3), "Updated Std": round(updated_std, 3),
                    })
                    new_cfg = dict(prior_cfg)
                    new_cfg["mean"] = str(updated_mean)
                    new_cfg["std"] = str(max(updated_std, 1e-6))
                    updated_params[key] = new_cfg

                st.dataframe(pd.DataFrame(update_rows), use_container_width=True)
                st.caption(
                    "Updated mean/std use a simple precision-weighted blend of the prior distribution "
                    "and the observed data (shrinking the prior toward the data as observations "
                    "accumulate) — a transparent approximation, not a full Bayesian conjugate update."
                )

                if st.button("Recompute Outputs with Updated Distributions", type="primary"):
                    with st.spinner("Recomputing…"):
                        try:
                            mon_results = run_simulation(
                                params=updated_params, iters=max(500, st.session_state.iters),
                                out_enabled=st.session_state.out_enabled, em_mode=st.session_state.em_mode,
                                tunnel_diam=st.session_state.tunnel_diam,
                                tunnel_radius=st.session_state.tunnel_radius,
                                insitu_stress=st.session_state.insitu_stress,
                                applied_stress_ratio=st.session_state.applied_stress_ratio,
                                corr_enabled=st.session_state.corr_enabled,
                                corr_pairs=st.session_state.corr_pairs,
                                ccm_method=st.session_state.ccm_method,
                                support_pressure_ratio=st.session_state.support_pressure_ratio,
                            )
                            st.session_state.monitoring_results = mon_results
                        except Exception as e:
                            st.error(f"Recompute error: {e}")

                mr = st.session_state.monitoring_results
                base = st.session_state.results
                if mr:
                    st.markdown("##### Updated vs. Original Output Statistics")
                    comp_rows = []
                    for o in ALL_OUTPUTS:
                        if not mr["out_enabled"].get(o["key"]):
                            continue
                        new_s = mr["o_stats"][o["key"]]
                        old_s = base["o_stats"][o["key"]] if base and base["out_enabled"].get(o["key"]) else None
                        comp_rows.append({
                            "Output": o["label"],
                            "Original Mean": round(old_s["mean"], 4) if old_s else "—",
                            "Updated Mean": round(new_s["mean"], 4),
                            "Original Std": round(old_s["std"], 4) if old_s else "—",
                            "Updated Std": round(new_s["std"], 4),
                        })
                    st.dataframe(pd.DataFrame(comp_rows), use_container_width=True)

    # ── FOOTER ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f"<div style='text-align:center;color:#607080;font-size:11px;'>"
        f"Rock Mass Variability Analysis v{APP_VERSION} · Monte Carlo Simulation · "
        "Barton Q (1974) · Bieniawski RMR (1989) · Hoek-Brown (1997) · "
        "Hoek-Diederichs (2006) · Serafim-Pereira (1983) · "
        "Iman &amp; Conover (1982) · Vanmarcke (1977) · Wang &amp; Cao (2014) · "
        "Carranza-Torres &amp; Fairhurst (1999) · Duncan Fama (1993) · Hoek (2000)"
        "</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
