"""Describe observed ESPN lineup roles without guessing missing slots."""


def roster_category(lineup_slot=None, *, free_agent=False):
    if free_agent:
        return "free_agent"
    slot = str(lineup_slot or "").strip().upper()
    if slot in {"BE", "BN", "BENCH", "IR", "ER", "ROOKIE", "RESERVE"}:
        return "bench"
    if slot in {"QB", "RB", "WR", "TE", "K", "PK", "DST", "D/ST",
                "RB/WR", "WR/TE", "RB/WR/TE", "FLEX", "SUPERFLEX", "OP"}:
        return "starter"
    return None
