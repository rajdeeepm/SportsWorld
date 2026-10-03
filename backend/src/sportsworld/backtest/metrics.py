from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

import numpy as np


def multiclass_brier(probabilities: np.ndarray, labels: np.ndarray) -> float:
    probabilities=np.asarray(probabilities,dtype=float); labels=np.asarray(labels,dtype=int)
    y=np.zeros_like(probabilities); y[np.arange(len(labels)),labels]=1.0
    return float(np.mean(np.sum((probabilities-y)**2,axis=1)))


def log_loss(probabilities: np.ndarray, labels: np.ndarray) -> float:
    probabilities=np.asarray(probabilities,dtype=float); labels=np.asarray(labels,dtype=int)
    chosen=np.clip(probabilities[np.arange(len(labels)),labels],1e-12,1.0)
    return -float(np.mean(np.log(chosen)))


def accuracy(probabilities: np.ndarray, labels: np.ndarray) -> float:
    return float(np.mean(np.argmax(probabilities,axis=1)==np.asarray(labels,dtype=int)))


def top_label_ece(probabilities: np.ndarray, labels: np.ndarray, bins: int=10) -> tuple[float,list[dict[str,float|int]]]:
    p=np.asarray(probabilities,dtype=float); y=np.asarray(labels,dtype=int); pred=np.argmax(p,axis=1); conf=np.max(p,axis=1); correct=(pred==y).astype(float); ece=0.0; rows=[]
    edges=np.linspace(0,1,bins+1)
    for i in range(bins):
        mask=(conf>=edges[i]) & (conf < edges[i+1] if i<bins-1 else conf<=edges[i+1])
        n=int(mask.sum())
        if n==0: rows.append({"bin_low":float(edges[i]),"bin_high":float(edges[i+1]),"count":0,"mean_confidence":0.0,"observed_accuracy":0.0}); continue
        mc=float(conf[mask].mean()); acc=float(correct[mask].mean()); ece += (n/len(y))*abs(mc-acc); rows.append({"bin_low":float(edges[i]),"bin_high":float(edges[i+1]),"count":n,"mean_confidence":mc,"observed_accuracy":acc})
    return float(ece),rows


def binary_reliability(home_prob: np.ndarray, labels: np.ndarray, bins:int=10)->list[dict[str,float|int]]:
    p=np.asarray(home_prob,dtype=float); y=np.asarray(labels,dtype=int); edges=np.linspace(0,1,bins+1); rows=[]
    for i in range(bins):
        mask=(p>=edges[i])&(p<(edges[i+1]) if i<bins-1 else p<=edges[i+1]); n=int(mask.sum())
        rows.append({"bin_low":float(edges[i]),"bin_high":float(edges[i+1]),"count":n,"mean_prediction":float(p[mask].mean()) if n else 0.0,"observed_frequency":float(y[mask].mean()) if n else 0.0})
    return rows


def interval_coverage(labels: np.ndarray, probabilities: np.ndarray, intervals: list[tuple[float,float]] | None=None) -> tuple[float,float]:
    if not intervals: return float("nan"),float("nan")
    covered=[]; widths=[]
    for y,p,(lo,hi) in zip(labels,probabilities,intervals):
        # For binary forecasts, coverage asks whether realized indicator falls
        # inside the reported probability interval; mainly useful when intervals
        # are interpreted as probability uncertainty, so retain as diagnostic.
        covered.append(float(lo <= float(y) <= hi)); widths.append(hi-lo)
    return float(np.mean(covered)),float(np.mean(widths))
