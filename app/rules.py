from datetime import datetime
import hashlib
import hmac

STATUSES = ('new', 'in_progress', 'closed')

def password_hash(password: str) -> str:
    # Fixed salt for reproducible educational demo accounts only.
    return hashlib.pbkdf2_hmac('sha256', password.encode(), b'denis_kuleshin_demo', 60000).hex()

def password_matches(password: str, stored: str) -> bool:
    return hmac.compare_digest(password_hash(password), stored)

def valid_transition(current: str, target: str) -> bool:
    return (current, target) in {('new', 'in_progress'), ('in_progress', 'closed')}

def reaction(created: datetime, comments: list[dict], limit_hours: int, now: datetime) -> dict:
    replies = [c['created_at'] for c in comments if c['is_staff']]
    first = min(replies) if replies else None
    hours = ((first or now) - created).total_seconds() / 3600
    return {'first_staff_reply': first, 'hours': round(hours, 3),
            'limit_hours': limit_hours, 'violated': hours > limit_hours}
