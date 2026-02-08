"""One-shot audit script: raw SQL -> repo -> service.

Run with: python scripts/audit_analytics.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure api/ is on sys.path when running from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text


async def audit():
    from core.database import create_engine, create_session_maker, init_db

    engine = create_engine()
    await init_db(engine)
    sm = create_session_maker(engine)
    async with sm() as db:
        # ── RAW SQL ──
        r = await db.execute(text("SELECT count(*) FROM users"))
        print(f"[RAW] users count: {r.scalar_one()}")

        r = await db.execute(text("SELECT count(*) FROM certificates"))
        print(f"[RAW] certificates count: {r.scalar_one()}")

        r = await db.execute(text("SELECT count(*) FROM step_progress"))
        print(f"[RAW] step_progress count: {r.scalar_one()}")

        r = await db.execute(text("SELECT count(*) FROM submissions"))
        print(f"[RAW] submissions count: {r.scalar_one()}")

        r = await db.execute(
            text("SELECT id, github_username, created_at FROM users LIMIT 5")
        )
        for row in r.all():
            print(f"[RAW] user: id={row[0]}, username={row[1]}, created_at={row[2]}")

        r = await db.execute(
            text("SELECT id, user_id, issued_at FROM certificates LIMIT 5")
        )
        for row in r.all():
            print(f"[RAW] cert: id={row[0]}, user_id={row[1]}, issued_at={row[2]}")

        r = await db.execute(
            text(
                "SELECT phase_id, topic_id, step_order, completed_at "
                "FROM step_progress ORDER BY completed_at DESC LIMIT 5"
            )
        )
        for row in r.all():
            print(
                f"[RAW] step: phase={row[0]}, topic={row[1]}, "
                f"step={row[2]}, completed_at={row[3]}"
            )

        r = await db.execute(
            text(
                "SELECT to_char(date_trunc('month', created_at), 'YYYY-MM'), count(*) "
                "FROM users GROUP BY 1 ORDER BY 1"
            )
        )
        print("[RAW] signups_by_month:", [(row[0], row[1]) for row in r.all()])

        r = await db.execute(
            text(
                "SELECT extract(isodow FROM completed_at)::int, count(*) "
                "FROM step_progress GROUP BY 1 ORDER BY 1"
            )
        )
        days = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
        print(
            "[RAW] activity_dow:",
            [(days.get(row[0], row[0]), row[1]) for row in r.all()],
        )

        r = await db.execute(
            text(
                "SELECT phase_id, count(DISTINCT user_id) "
                "FROM step_progress GROUP BY 1 ORDER BY 1"
            )
        )
        print("[RAW] users_reached:", [(row[0], row[1]) for row in r.all()])

        # ── REPO LAYER ──
        print("\n=== REPO LAYER ===")
        from repositories.analytics_repository import AnalyticsRepository

        repo = AnalyticsRepository(db)
        print(f"total_users: {await repo.get_total_users()}")
        print(f"total_certs: {await repo.get_total_certificates()}")
        print(f"active_30d: {await repo.get_active_learners(days=30)}")
        print(f"histogram: {await repo.get_step_completion_histogram()}")
        print(f"signups: {await repo.get_signups_by_month()}")
        print(f"certs_monthly: {await repo.get_certificates_by_month()}")
        print(f"submissions: {await repo.get_submission_stats_by_phase()}")
        print(f"activity_dow: {await repo.get_activity_by_day_of_week()}")

        # ── SERVICE LAYER ──
        print("\n=== SERVICE LAYER ===")
        from services.analytics_service import get_community_analytics

        a = await get_community_analytics(db)
        print(f"total_users: {a.total_users}")
        print(f"total_certs: {a.total_certificates}")
        print(f"active_30d: {a.active_learners_30d}")
        print(f"completion_rate: {a.completion_rate}%")
        pd = [
            (p.phase_name, p.users_reached, p.users_completed_steps)
            for p in a.phase_distribution
        ]
        print(f"phase_dist: {pd}")
        st = [(t.month, t.count, t.cumulative) for t in a.signup_trends]
        print(f"signup_trends: {st}")
        ct = [(t.month, t.count, t.cumulative) for t in a.certificate_trends]
        print(f"cert_trends: {ct}")
        ad = [(d.day_name, d.completions) for d in a.activity_by_day]
        print(f"activity: {ad}")

    await engine.dispose()


asyncio.run(audit())
