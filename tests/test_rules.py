from datetime import datetime,timezone,timedelta
import pytest
from app.rules import reaction,valid_transition

CREATED=datetime(2026,10,1,tzinfo=timezone.utc)

def test_first_reply_is_from_staff_not_user():
    comments=[{'created_at':CREATED+timedelta(minutes=2),'is_staff':False},
              {'created_at':CREATED+timedelta(hours=3),'is_staff':True},
              {'created_at':CREATED+timedelta(hours=1),'is_staff':True}]
    r=reaction(CREATED,comments,2,CREATED+timedelta(days=1))
    assert r['hours']==1 and not r['violated']

def test_reply_exactly_at_limit_is_not_violation():
    r=reaction(CREATED,[{'created_at':CREATED+timedelta(hours=2),'is_staff':True}],2,CREATED)
    assert not r['violated']

def test_late_staff_reply_is_violation():
    r=reaction(CREATED,[{'created_at':CREATED+timedelta(hours=3),'is_staff':True}],2,CREATED)
    assert r['violated']

def test_no_reply_uses_elapsed_wait():
    r=reaction(CREATED,[],2,CREATED+timedelta(hours=3))
    assert r['first_staff_reply'] is None and r['violated']

def test_status_follows_workflow():
    assert valid_transition('new','in_progress')
    assert valid_transition('in_progress','closed')

def test_invalid_status_transition_rejected():
    assert not valid_transition('new','closed')
    assert not valid_transition('closed','new')
