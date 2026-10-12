"""Display-only selection of frozen original time centers; not a trading signal."""
from __future__ import annotations

import pandas as pd

from .multiclock import WINDOW_COLUMNS

KEY_POINT_COLUMNS = [
    "date", "priority_rank", "window_count", "source_family_count",
    "independent_family_count", "center_member_count", "source_families",
    "causal_families", "clocks", "session_status", "center_window_ids",
    "active_window_ids", "center_anchors", "center_confirm_dates",
]
MEMBER_COLUMNS = ["key_date", "is_exact_center", *WINDOW_COLUMNS]


def _joined(values: pd.Series) -> str:
    return "|".join(sorted(set(values.dropna().astype(str))))


def select_time_key_points(
    windows: pd.DataFrame,
    sessions: pd.DataFrame,
    as_of: str | pd.Timestamp,
    projection_end: str | pd.Timestamp,
    *,
    max_points: int = 8,
    min_members: int = 3,
    min_causal_families: int = 2,
    separation: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank primary-window original centers and suppress nearby lower priorities.

    All confirmation filters use the frozen snapshot. Primary natural tolerance
    is at most two days, trading centers must use an exchange calendar, and
    shared price-pivot clocks retain their conservative single causal family.
    Tolerances/intervals are returned only in the member audit, never the list.
    Changes to display parameters must be declared before examining outcomes.
    """
    if min(max_points, min_members, min_causal_families) < 1 or separation < 0:
        raise ValueError("selection limits must be positive; separation must be nonnegative")
    empty = (pd.DataFrame(columns=KEY_POINT_COLUMNS), pd.DataFrame(columns=MEMBER_COLUMNS))
    if windows.empty:
        return empty
    as_of, projection_end = pd.Timestamp(as_of).normalize(), pd.Timestamp(projection_end).normalize()
    w = windows.copy()
    for column in ("anchor_date", "confirm_date", "center_date", "start_date", "end_date"):
        w[column] = pd.to_datetime(w[column]).dt.normalize()
    s = sessions.copy()
    s["date"] = pd.to_datetime(s["date"]).dt.normalize()
    valid_sessions = s.loc[s["session_status"].isin(["observed", "exchange_calendar"])]
    statuses = valid_sessions.set_index("date")["session_status"].to_dict()
    session_positions = {date: i for i, date in enumerate(sorted(statuses))}
    has_future_calendar = bool((valid_sessions["date"] > as_of).any())

    natural = w["clock"].eq("natural_day")
    trading = w["clock"].eq("trading_bar")
    primary = (natural & (pd.to_numeric(w["tolerance"]) <= 2)) | trading
    causal = (
        w["anchor_date"].le(w["confirm_date"])
        & w["confirm_date"].le(as_of)
        & w["confirm_date"].lt(w["center_date"])
        & w["start_date"].le(w["end_date"])
    )
    # Do not allow estimated trading clocks even as overlap contributors.
    calendar_ok = natural | (
        trading & w["calendar_status"].isin(["observed", "exchange_calendar"])
        & w["center_date"].isin(statuses)
    )
    w = w.loc[primary & causal & calendar_ok].copy()
    # The window id is shared by sensitivity variants: count each clock once.
    w = w.sort_values(["window_id", "tolerance"]).drop_duplicates("window_id")
    centers = w.loc[
        w["center_date"].gt(as_of) & w["center_date"].le(projection_end)
        & w["start_date"].le(w["center_date"]) & w["end_date"].ge(w["center_date"]),
        "center_date",
    ].drop_duplicates().sort_values()
    rows = []
    for date in centers:
        active = w.loc[w["start_date"].le(date) & w["end_date"].ge(date)]
        exact = active.loc[active["center_date"].eq(date)]
        count, families = active["window_id"].nunique(), active["causal_family"].nunique()
        if count < min_members and families < min_causal_families:
            continue
        status = statuses.get(date)
        if status is None:
            status = "natural_nontrading_day" if has_future_calendar else "natural_calendar_unverified"
        rows.append({
            "date": date, "window_count": count,
            "source_family_count": active["source_family"].nunique(),
            "independent_family_count": families, "center_member_count": len(exact),
            "source_families": _joined(active["source_family"]),
            "causal_families": _joined(active["causal_family"]),
            "clocks": _joined(active["clock"]), "session_status": status,
            "center_window_ids": _joined(exact["window_id"]),
            "active_window_ids": _joined(active["window_id"]),
            "center_anchors": _joined(exact["anchor_date"].dt.strftime("%Y-%m-%d")),
            "center_confirm_dates": _joined(exact["confirm_date"].dt.strftime("%Y-%m-%d")),
        })
    if not rows:
        return empty
    ranked = pd.DataFrame(rows).sort_values(
        ["independent_family_count", "source_family_count", "window_count", "center_member_count", "date"],
        ascending=[False, False, False, False, True],
    )
    ranked["priority_rank"] = range(1, len(ranked) + 1)

    def nearby(left: pd.Timestamp, right: pd.Timestamp) -> bool:
        if left in session_positions and right in session_positions:
            return abs(session_positions[left] - session_positions[right]) <= separation
        return abs((left - right).days) <= separation

    chosen = []
    for row in ranked.to_dict("records"):
        if any(nearby(row["date"], prior["date"]) for prior in chosen):
            continue
        chosen.append(row)
        if len(chosen) >= max_points:
            break
    points = pd.DataFrame(chosen).reindex(columns=KEY_POINT_COLUMNS).sort_values("date").reset_index(drop=True)
    member_frames = []
    for date in points["date"]:
        active = w.loc[w["start_date"].le(date) & w["end_date"].ge(date)].copy()
        active["key_date"] = date
        active["is_exact_center"] = active["center_date"].eq(date)
        member_frames.append(active.reindex(columns=MEMBER_COLUMNS))
    members = pd.concat(member_frames, ignore_index=True) if member_frames else empty[1]
    return points, members
