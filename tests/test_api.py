from datetime import datetime,timezone
from fastapi.testclient import TestClient
import pytest
from app.main import app,get_store
from app.rules import password_hash

class FakeStore:
    """Prepared data for unit contract checks; PostgreSQL is exercised manually after seeding."""
    def __init__(self):
        self.status='new'
        self.now=datetime(2026,10,1,tzinfo=timezone.utc)
    def one(self,sql,params=()):
        if 'FROM users' in sql:
            return {'id':1,'username':'demo_staff','password_hash':password_hash('demo'),'is_staff':True} if params[0]=='demo_staff' else None
        if 'count(*) AS n' in sql:return {'n':300}
        if 'FROM categories WHERE' in sql:return {'id':1} if params[0]==1 else None
        if 'FROM tickets t JOIN' in sql:
            return {'id':1,'status':self.status,'created_at':self.now,'reaction_hours':2} if params[0]==1 else None
        if sql.startswith('INSERT INTO tickets'):return {'id':301,'status':'new','title':params[2],'category_id':params[1]}
        if sql.startswith('UPDATE tickets'):
            self.status=params[0];return {'id':1,'status':self.status}
        if sql.startswith('INSERT INTO comments'):return {'id':901,'body':params[2]}
        raise AssertionError(sql)
    def query(self,sql,params=()):
        if sql.startswith('WITH first_reply'):
            return [{'id':1,'name':'Категория 1','reaction_hours':2,'open_count':10,'violated_count':2}]
        if 'FROM comments' in sql:return []
        if 'FROM categories ORDER' in sql:return [{'id':1,'name':'Категория 1','reaction_hours':2}]
        if 'FROM tickets t JOIN' in sql:return [{'id':i,'title':f'Заявка {i}'} for i in range(1,params[-2]+1)]
        raise AssertionError(sql)

@pytest.fixture
def client():
    store=FakeStore()
    app.dependency_overrides[get_store]=lambda:store
    with TestClient(app) as c:yield c
    app.dependency_overrides.clear()

def sign_in(client):
    r=client.post('/api/login',json={'username':'demo_staff','password':'demo'})
    assert r.status_code==200

def test_authorization_required(client):
    assert client.get('/api/tickets').status_code==401

def test_bad_password_rejected(client):
    assert client.post('/api/login',json={'username':'demo_staff','password':'wrong'}).status_code==401

def test_list_pagination_and_fields(client):
    sign_in(client)
    r=client.get('/api/tickets?page=1&size=20&status=new')
    assert r.status_code==200
    assert len(r.json()['items'])==20 and r.json()['total']==300

def test_invalid_page(client):
    sign_in(client)
    assert client.get('/api/tickets?page=0').status_code==422

def test_categories(client):
    sign_in(client)
    assert client.get('/api/categories').json()['items'][0]['reaction_hours']==2

def test_create_and_unknown_category(client):
    sign_in(client)
    payload={'title':'Проверка','body':'Описание','category_id':1}
    r=client.post('/api/tickets',json=payload)
    assert r.status_code==201 and r.json()['status']=='new'
    payload['category_id']=999
    assert client.post('/api/tickets',json=payload).status_code==404

def test_empty_title(client):
    sign_in(client)
    assert client.post('/api/tickets',json={'title':' ','body':'Текст','category_id':1}).status_code==422

def test_card_and_not_found(client):
    sign_in(client)
    r=client.get('/api/tickets/1')
    assert r.status_code==200 and {'ticket','comments','reaction'}<=r.json().keys()
    assert client.get('/api/tickets/999').status_code==404

def test_status_transitions(client):
    sign_in(client)
    assert client.patch('/api/tickets/1/status',json={'status':'closed'}).status_code==400
    assert client.patch('/api/tickets/1/status',json={'status':'in_progress'}).status_code==200
    assert client.patch('/api/tickets/1/status',json={'status':'closed'}).json()['status']=='closed'

def test_comment_validation(client):
    sign_in(client)
    assert client.post('/api/tickets/1/comments',json={'body':'Ответ'}).status_code==201
    assert client.post('/api/tickets/1/comments',json={'body':' '}).status_code==422

def test_summary_share(client):
    sign_in(client)
    r=client.get('/api/summary')
    assert r.status_code==200 and r.json()['items'][0]['violated_share']==.2

def test_logout(client):
    sign_in(client)
    assert client.post('/api/logout').status_code==200
    assert client.get('/api/summary').status_code==401

def test_diagnostic_headers(client):
    sign_in(client)
    r=client.get('/api/categories')
    assert float(r.headers['X-App-Ms'])>=0
    assert 'X-Db-Ms' in r.headers and 'X-Sql-Count' in r.headers
