#!/usr/bin/env python3
"""Seed a local certificate row for testing.

This is intended for LOCAL development only.

Usage:
    cd api
    .venv/bin/python -m scripts.seed_test_certificate --user-id <clerk_user_id>

Then you can test public verify endpoints with the printed verification code:
    GET /api/certificates/verify/<code>
    GET /api/certificates/verify/<code>/pdf
    GET /api/certificates/verify/<code>/svg
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from uuid import uuid4

# Add parent directory to path so we can import from core/models regardless of cwd
sys.path.insert(0, str(__file__).rsplit("/scripts", 1)[0])

from sqlalchemy import select

from core.database import get_session_maker
from models import Certificate, User


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a test certificate")
    parser.add_argument(
        "--user-id",
        required=True,
        help=(
            "Clerk user id (must match your local auth user id if you want it "
            "to show up in /certificates)"
        ),
    )
    parser.add_argument(
        "--email",
        default="test@example.com",
        help="Email used when creating the user if it does not exist",
    )
    parser.add_argument(
        "--recipient-name",
        default="Test User",
        help="Name printed on the certificate",
    )
    parser.add_argument(
        "--certificate-type",
        default="full_completion",
        help="Certificate type (default: full_completion)",
    )
    parser.add_argument(
        "--phases-completed",
        type=int,
        default=7,
        help="Number of phases completed to store on the certificate",
    )
    parser.add_argument(
        "--total-phases",
        type=int,
        default=7,
        help="Total phases to store on the certificate",
    )
    return parser.parse_args()


async def seed_test_certificate() -> None:
    args = _parse_args()

    session_maker = get_session_maker()
    async with session_maker() as session:
        user = await session.get(User, args.user_id)
        if user is None:
            user = User(
                id=args.user_id,
                email=args.email,
                first_name=args.recipient_name.split(" ", 1)[0],
                last_name=(
                    args.recipient_name.split(" ", 1)[1]
                    if " " in args.recipient_name
                    else None
                ),
            )
            session.add(user)
            await session.flush()

        existing = await session.execute(
            select(Certificate).where(
                Certificate.user_id == args.user_id,
                Certificate.certificate_type == args.certificate_type,
            )
        )
        existing_cert = existing.scalar_one_or_none()
        if existing_cert is not None:
            print(
                "Certificate already exists for user/type. "
                f"id={existing_cert.id} "
                f"verification_code={existing_cert.verification_code}"
            )
            return

        verification_code = uuid4().hex
        certificate = Certificate(
            user_id=args.user_id,
            certificate_type=args.certificate_type,
            verification_code=verification_code,
            recipient_name=args.recipient_name,
            issued_at=datetime.now(UTC),
            phases_completed=args.phases_completed,
            total_phases=args.total_phases,
        )
        session.add(certificate)
        await session.commit()

        print("Seeded certificate:")
        print(f"  user_id: {args.user_id}")
        print(f"  certificate_type: {args.certificate_type}")
        print(f"  verification_code: {verification_code}")


if __name__ == "__main__":
    asyncio.run(seed_test_certificate())
