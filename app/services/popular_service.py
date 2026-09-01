"""Popular traffic view model: podium (admin-set 1·2·3) + rest by efficiency (excludes applied)."""
from ..models import media as media_model
from ..models import popular as popular_model


def build(channel, category_id):
    cat = popular_model.get_category(category_id)
    if not cat or cat["channel"] != channel:
        return None
    sets = popular_model.sets_for(category_id)
    meta = popular_model.meta_for(category_id) or {"show_weekly_cnt": 1, "updated_at": None}
    weekly = popular_model.weekly_counts(channel)
    top_ids = set()
    for s in sets:
        s["eff"] = s["efficiency_manual"] if s["efficiency_manual"] is not None else s["efficiency_auto"]
        s["weekly"] = weekly.get(s["media_id"], 0)
        top_ids.add(s["media_id"])
    excludes = popular_model.excludes_for(category_id)
    rest = []
    for m in media_model.list_by_channel(channel):
        if m["id"] in top_ids or m["id"] in excludes:
            continue
        m["eff"] = media_model.efficiency(m)
        rest.append(m)
    rest.sort(key=lambda m: -m["eff"])
    return {"category": cat, "sets": sets, "rest": rest, "meta": meta}
