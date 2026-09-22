"""차트 패턴(컵 위드 핸들, 헤드 앤 숄더 등) 후보를 실제 가격 데이터에서 찾는
간단한 규칙 기반 탐지기. 정밀한 패턴 인식 알고리즘이 아니라, 국소 고점·저점의
기하학적 배치를 느슨한 허용오차로 확인하는 학습용 근사 탐지기다. '패턴처럼 보이는
구간을 찾아 보여주는 것'이 목적이며, 실제 매매 신호를 생성하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import argrelextrema


@dataclass
class KeyPoint:
    index: int
    label: str


@dataclass
class PatternMatch:
    pattern: str
    start_index: int
    end_index: int
    breakout_index: int | None
    key_points: list[KeyPoint]
    neckline: tuple[float, float] | None  # (start_price, end_price) at start/end index of neckline span
    neckline_span: tuple[int, int] | None
    score: float
    direction: str  # "bullish" | "bearish"
    summary: str


def _extrema(values: np.ndarray, order: int = 5) -> tuple[np.ndarray, np.ndarray]:
    peaks = argrelextrema(values, np.greater_equal, order=order)[0]
    troughs = argrelextrema(values, np.less_equal, order=order)[0]
    # 평평한 구간에서 같은 값이 연속으로 극값 처리되는 것을 정리한다.
    peaks = np.array([i for i in peaks if 0 < i < len(values) - 1])
    troughs = np.array([i for i in troughs if 0 < i < len(values) - 1])
    return peaks, troughs


def detect_head_and_shoulders(values: np.ndarray, order: int = 5) -> list[PatternMatch]:
    peaks, troughs = _extrema(values, order)
    matches: list[PatternMatch] = []
    if len(peaks) < 3:
        return matches
    for i in range(len(peaks) - 2):
        p1, p2, p3 = peaks[i], peaks[i + 1], peaks[i + 2]
        v1, v2, v3 = values[p1], values[p2], values[p3]
        if not (v2 > v1 * 1.02 and v2 > v3 * 1.02):
            continue
        shoulder_diff = abs(v1 - v3) / max(v1, v3)
        if shoulder_diff > 0.08:
            continue
        t_between_12 = troughs[(troughs > p1) & (troughs < p2)]
        t_between_23 = troughs[(troughs > p2) & (troughs < p3)]
        if len(t_between_12) == 0 or len(t_between_23) == 0:
            continue
        t1, t2 = t_between_12[-1], t_between_23[0]
        neck1, neck2 = values[t1], values[t2]
        neck_diff = abs(neck1 - neck2) / max(neck1, neck2)
        if neck_diff > 0.08:
            continue
        neckline_at = neck1 + (neck2 - neck1) * 0  # placeholder, linear interp done at use site
        breakout_index = None
        search_end = min(len(values), p3 + max(20, (p3 - p1)))
        for j in range(p3, search_end):
            neck_level = neck1 + (neck2 - neck1) * ((j - t1) / (t2 - t1)) if t2 != t1 else neck1
            if values[j] < neck_level * 0.995:
                breakout_index = j
                break
        score = 1.0 - shoulder_diff - neck_diff + (0.3 if breakout_index else 0)
        matches.append(PatternMatch(
            pattern="head_shoulders", start_index=int(p1), end_index=int(breakout_index or p3),
            breakout_index=breakout_index,
            key_points=[KeyPoint(int(p1), "왼쪽 어깨"), KeyPoint(int(t1), "목선①"), KeyPoint(int(p2), "머리"),
                        KeyPoint(int(t2), "목선②"), KeyPoint(int(p3), "오른쪽 어깨")],
            neckline=(float(neck1), float(neck2)), neckline_span=(int(t1), int(t2)),
            score=score, direction="bearish",
            summary=f"왼쪽/오른쪽 어깨 높이 차이 {shoulder_diff*100:.1f}%, 목선 기울기 차이 {neck_diff*100:.1f}%",
        ))
    return matches


def detect_inverse_head_and_shoulders(values: np.ndarray, order: int = 5) -> list[PatternMatch]:
    inverted = -values
    raw = detect_head_and_shoulders(inverted, order)
    matches = []
    for m in raw:
        neck1, neck2 = (-m.neckline[0], -m.neckline[1]) if m.neckline else (None, None)
        matches.append(PatternMatch(
            pattern="inverse_head_shoulders", start_index=m.start_index, end_index=m.end_index,
            breakout_index=m.breakout_index,
            key_points=[KeyPoint(kp.index, kp.label.replace("어깨", "어깨").replace("머리", "머리"))
                        for kp in m.key_points],
            neckline=(neck1, neck2) if neck1 is not None else None, neckline_span=m.neckline_span,
            score=m.score, direction="bullish", summary=m.summary,
        ))
    return matches


def detect_double_top(values: np.ndarray, order: int = 5) -> list[PatternMatch]:
    peaks, troughs = _extrema(values, order)
    matches: list[PatternMatch] = []
    for i in range(len(peaks) - 1):
        p1, p2 = peaks[i], peaks[i + 1]
        v1, v2 = values[p1], values[p2]
        diff = abs(v1 - v2) / max(v1, v2)
        if diff > 0.03:
            continue
        between = troughs[(troughs > p1) & (troughs < p2)]
        if len(between) == 0:
            continue
        t = between[np.argmin(values[between])]
        retrace = (v1 - values[t]) / v1
        if retrace < 0.04:
            continue
        breakout_index = None
        search_end = min(len(values), p2 + max(20, (p2 - p1)))
        for j in range(p2, search_end):
            if values[j] < values[t] * 0.995:
                breakout_index = j
                break
        score = 1.0 - diff + retrace + (0.3 if breakout_index else 0)
        matches.append(PatternMatch(
            pattern="double_top", start_index=int(p1), end_index=int(breakout_index or p2),
            breakout_index=breakout_index,
            key_points=[KeyPoint(int(p1), "첫 번째 고점"), KeyPoint(int(t), "저점(넥라인)"), KeyPoint(int(p2), "두 번째 고점")],
            neckline=(float(values[t]), float(values[t])), neckline_span=(int(t), int(p2)),
            score=score, direction="bearish",
            summary=f"두 고점 차이 {diff*100:.1f}%, 되돌림 {retrace*100:.1f}%",
        ))
    return matches


def detect_double_bottom(values: np.ndarray, order: int = 5) -> list[PatternMatch]:
    raw = detect_double_top(-values, order)
    matches = []
    for m in raw:
        neck = -m.neckline[0] if m.neckline else None
        matches.append(PatternMatch(
            pattern="double_bottom", start_index=m.start_index, end_index=m.end_index,
            breakout_index=m.breakout_index,
            key_points=[KeyPoint(kp.index, kp.label.replace("고점", "저점").replace("저점(넥라인)", "고점(넥라인)"))
                        for kp in m.key_points],
            neckline=(neck, neck) if neck is not None else None, neckline_span=m.neckline_span,
            score=m.score, direction="bullish", summary=m.summary,
        ))
    return matches


def detect_triangle(values: np.ndarray, order: int = 4, window: int = 60) -> list[PatternMatch]:
    matches: list[PatternMatch] = []
    n = len(values)
    step = 10
    for start in range(0, max(1, n - window), step):
        end = min(n, start + window)
        segment = values[start:end]
        peaks, troughs = _extrema(segment, order)
        if len(peaks) < 2 or len(troughs) < 2:
            continue
        peak_slope = np.polyfit(peaks, segment[peaks], 1)[0]
        trough_slope = np.polyfit(troughs, segment[troughs], 1)[0]
        avg_price = float(np.mean(segment))
        norm_peak_slope = peak_slope / avg_price
        norm_trough_slope = trough_slope / avg_price
        converging = norm_peak_slope < -0.0005 and norm_trough_slope > 0.0005
        if not converging:
            continue
        last_idx = end - 1
        breakout_index = None
        breakout_dir = None
        for j in range(last_idx, min(n, last_idx + 15)):
            peak_line = np.polyval(np.polyfit(peaks, segment[peaks], 1), j - start)
            trough_line = np.polyval(np.polyfit(troughs, segment[troughs], 1), j - start)
            if values[j] > peak_line * 1.01:
                breakout_index, breakout_dir = j, "bullish"
                break
            if values[j] < trough_line * 0.99:
                breakout_index, breakout_dir = j, "bearish"
                break
        score = abs(norm_peak_slope) + abs(norm_trough_slope) + (0.3 if breakout_index else 0)
        matches.append(PatternMatch(
            pattern="triangle", start_index=int(start), end_index=int(breakout_index or end - 1),
            breakout_index=breakout_index,
            key_points=[KeyPoint(int(start + p), "저항선 고점") for p in peaks]
                       + [KeyPoint(int(start + t), "지지선 저점") for t in troughs],
            neckline=None, neckline_span=None,
            score=score, direction=breakout_dir or "neutral",
            summary=f"고점선 기울기 {norm_peak_slope*100:.2f}%/봉, 저점선 기울기 {norm_trough_slope*100:.2f}%/봉",
        ))
    return matches


def detect_cup_with_handle(values: np.ndarray, order: int = 5) -> list[PatternMatch]:
    peaks, troughs = _extrema(values, order)
    matches: list[PatternMatch] = []
    for i in range(len(peaks) - 1):
        left_rim = peaks[i]
        later_peaks = peaks[peaks > left_rim]
        if len(later_peaks) == 0:
            continue
        cup_troughs = troughs[troughs > left_rim]
        if len(cup_troughs) == 0:
            continue
        bottom = cup_troughs[np.argmin(values[cup_troughs])]
        right_candidates = later_peaks[later_peaks > bottom]
        if len(right_candidates) == 0:
            continue
        right_rim = right_candidates[0]
        rim_diff = abs(values[left_rim] - values[right_rim]) / values[left_rim]
        cup_depth = (values[left_rim] - values[bottom]) / values[left_rim]
        if rim_diff > 0.07 or cup_depth < 0.12:
            continue
        handle_troughs = troughs[(troughs > right_rim)]
        if len(handle_troughs) == 0:
            continue
        handle_bottom = handle_troughs[0]
        handle_depth = (values[right_rim] - values[handle_bottom]) / values[right_rim]
        if handle_depth > cup_depth * 0.6 or handle_depth < 0.01:
            continue
        breakout_index = None
        search_end = min(len(values), handle_bottom + 20)
        for j in range(handle_bottom, search_end):
            if values[j] > values[right_rim] * 1.005:
                breakout_index = j
                break
        score = 1.0 - rim_diff + cup_depth + (0.3 if breakout_index else 0)
        matches.append(PatternMatch(
            pattern="cup_with_handle", start_index=int(left_rim), end_index=int(breakout_index or handle_bottom),
            breakout_index=breakout_index,
            key_points=[KeyPoint(int(left_rim), "컵 왼쪽 가장자리"), KeyPoint(int(bottom), "컵 바닥"),
                        KeyPoint(int(right_rim), "컵 오른쪽 가장자리"), KeyPoint(int(handle_bottom), "손잡이 저점")],
            neckline=(float(values[right_rim]), float(values[right_rim])), neckline_span=(int(right_rim), int(handle_bottom)),
            score=score, direction="bullish",
            summary=f"컵 깊이 {cup_depth*100:.1f}%, 양쪽 가장자리 차이 {rim_diff*100:.1f}%, 손잡이 되돌림 {handle_depth*100:.1f}%",
        ))
    return matches


DETECTORS = {
    "cup_with_handle": detect_cup_with_handle,
    "head_shoulders": detect_head_and_shoulders,
    "inverse_head_shoulders": detect_inverse_head_and_shoulders,
    "double_top": detect_double_top,
    "double_bottom": detect_double_bottom,
    "triangle": detect_triangle,
}
