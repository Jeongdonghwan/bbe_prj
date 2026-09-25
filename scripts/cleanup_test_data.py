"""시드가 심어둔 테스트 데이터 정리 (매체 "테스트 N" 과 거기에 달린 캠페인).

    python scripts/cleanup_test_data.py          # 무엇이 지워질지 보여만 준다
    python scripts/cleanup_test_data.py --yes    # 실제로 지운다

실제 캠페인이 걸린 매체는 건드리지 않는다. 크레딧 원장은 회계 기록이라 남기되,
아직 안 돌려준 크레딧이 있으면 먼저 환불한 뒤 캠페인을 지운다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.db import query  # noqa: E402
from app.models import campaign as campaign_model  # noqa: E402
from app.services import credit_service  # noqa: E402

REFUNDABLE = ("review", "approved", "running")


def main():
    apply = "--yes" in sys.argv
    app = create_app()
    with app.app_context():
        medias = query("SELECT id, channel, name FROM media WHERE name LIKE '테스트 %' ORDER BY channel, id")
        if not medias:
            print("테스트 매체가 없습니다.")
            return 0
        ids = [m["id"] for m in medias]
        ph = ",".join(["%s"] * len(ids))
        camps = query(f"""SELECT id, order_no, user_id, status, pay_method, paid_amount, refund_amount
                          FROM campaigns WHERE media_id IN ({ph}) ORDER BY id""", ids)
        refunds = [c for c in camps
                   if c["status"] in REFUNDABLE and c["pay_method"] == "credit"
                   and (c["paid_amount"] or 0) - (c["refund_amount"] or 0) > 0]

        print(f"테스트 매체 {len(medias)}개: " + ", ".join(f"{m['channel']}/{m['name']}" for m in medias))
        print(f"딸린 캠페인 {len(camps)}건" + (f" (그중 {len(refunds)}건은 환불 후 삭제)" if refunds else ""))
        for c in refunds:
            out = (c["paid_amount"] or 0) - (c["refund_amount"] or 0)
            print(f"  - {c['order_no']} {c['status']} → {out:,}원 환불")
        if not apply:
            print("\n실제로 지우려면: python scripts/cleanup_test_data.py --yes")
            return 0

        for c in refunds:
            out = (c["paid_amount"] or 0) - (c["refund_amount"] or 0)
            credit_service.refund(c["user_id"], out, c["id"], f"테스트 데이터 정리 · {c['order_no']}")
        for c in camps:
            campaign_model.purge(c["id"])
        # 인기 트래픽 설정이 테스트 매체를 가리키고 있으면 함께 정리
        from app.db import execute
        execute(f"DELETE FROM popular_sets WHERE media_id IN ({ph})", ids)
        execute(f"DELETE FROM popular_excludes WHERE media_id IN ({ph})", ids)
        execute(f"DELETE FROM weekly_ranks WHERE type_id IN ({ph})", ids)
        execute(f"DELETE FROM reviews WHERE type_id IN ({ph})", ids)
        execute(f"DELETE FROM media WHERE id IN ({ph})", ids)
        print(f"\n삭제 완료 — 매체 {len(medias)}개, 캠페인 {len(camps)}건, 환불 {len(refunds)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
