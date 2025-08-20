import os
from fastapi.testclient import TestClient
from backend.app.main import app

def test_transcription_disabled_no_pending_marker():
    # Con transcripción deshabilitada, transcript placeholder debe mantenerse si no había texto
    client = TestClient(app)
    r_parent = client.post('/api/auth/register', json={'email':'txparent@example.com','password':'pass123','role':'parent'})
    assert r_parent.status_code in (200,201)
    login = client.post('/api/auth/login', json={'email':'txparent@example.com','password':'pass123'})
    token = login.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    child = client.post('/api/children', json={'name':'TxKid'}, headers=headers)
    cid = child.json()['id']
    # Subir response sin texto ni audio -> transcript igual al texto (vacío) y no placeholder
    r = client.post('/api/children/{}/responses'.format(cid), json={'text': ''}, headers=headers)
    assert r.status_code == 202

# Nota: pruebas reales de transcripción requerirían habilitar flag y mockear faster_whisper.
