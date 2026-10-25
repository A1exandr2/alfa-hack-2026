"""Server-console provisioning; credentials arrive via stdin or environment, never argv."""
import argparse
import asyncio
import json
import os
import sys
from uuid import UUID
from sqlalchemy import select
from app.auth.security import hash_password
from app.database import session_factory, engine
from app.models import AdminAudit, User


async def provision(data, rotate_id=None, if_missing=False):
    email, password = data['email'].strip().lower(), data['password']
    if len(password) < 20 or len(password) > 128 or '@' not in email:
        raise ValueError('Use an email and a password of 20–128 characters')
    async with session_factory() as session:
        if rotate_id:
            user = await session.scalar(select(User).where(User.id == rotate_id).with_for_update())
            if not user or user.role != 'ADMIN':
                raise ValueError('Existing administrator not found; no changes made')
            other = await session.scalar(select(User.id).where(User.email == email, User.id != user.id))
            if other:
                raise ValueError('Email belongs to another account; no changes made')
            user.email, user.password_hash = email, hash_password(password)
            user.full_name = data.get('full_name', 'Admin')
            action = 'ADMIN_CREDENTIALS_ROTATED'
        else:
            existing = await session.scalar(select(User).where(User.email == email))
            if existing is not None:
                if if_missing and existing.role == 'ADMIN':
                    print('Administrator already exists; password and access left unchanged.')
                    return
                raise ValueError('Account already exists; no changes made')
            user = User(email=email, password_hash=hash_password(password), full_name=data.get('full_name', 'Admin'), role='ADMIN', is_active=True)
            session.add(user)
            await session.flush()
            action = 'ADMIN_CREATED'
        session.add(AdminAudit(actor_user_id=user.id, actor_email=user.email, action=action,
                               target_id=user.id, details={'source':'server_console'}))
        await session.commit()
    print('Administrator provisioned. Credentials were not logged.')


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-env', action='store_true')
    parser.add_argument('--rotate-existing', type=UUID)
    parser.add_argument('--if-missing', action='store_true')
    args = parser.parse_args()
    data = {'email':os.environ.get('ADMIN_EMAIL',''), 'password':os.environ.get('ADMIN_PASSWORD',''),
            'full_name':'Admin'} if args.from_env else json.load(sys.stdin)
    try:
        await provision(data, args.rotate_existing, args.if_missing)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
