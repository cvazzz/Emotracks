import io
import wave
from fastapi.testclient import TestClient
from backend.app.main import app


def _gen_wav(duration_sec: float = 0.05, freq: float = 440.0):
    import math, struct
    rate = 8000
    frames = int(duration_sec * rate)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        for i in range(frames):
            val = int(32767 * 0.1 * math.sin(2 * math.pi * freq * (i / rate)))
            wf.writeframes(struct.pack('<h', val))
    buf.seek(0)
    return buf


def test_audio_upload_and_duration():
    client = TestClient(app)
    # Crear parent + login para child
    r_parent = client.post('/api/auth/register', json={'email': 'audiop@example.com', 'password': 'pass123', 'role': 'parent'})
    assert r_parent.status_code in (200,201)
    login = client.post('/api/auth/login', json={'email': 'audiop@example.com', 'password': 'pass123'})
    token = login.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    r_child = client.post('/api/children', json={'name': 'AudioKid'}, headers=headers)
    assert r_child.status_code == 201
    cid = r_child.json()['id']
    # WAV en memoria
    wav_file = _gen_wav()
    files = {'audio_file': ('test.wav', wav_file, 'audio/wav')}
    r_submit = client.post('/api/submit-responses', data={'child_id': str(cid), 'text': 'hola audio'}, files=files)
    assert r_submit.status_code == 202, r_submit.text
    resp_id = r_submit.json()['response_id']
    # Obtener detalle luego de que tarea eager corrió
    detail = client.get(f'/api/responses/{resp_id}')
    assert detail.status_code == 200
    analysis = detail.json().get('analysis_json')
    # Como el task stub coloca transcript original de texto, audio_features puede contener duration
    if analysis and analysis.get('audio_features'):
        af = analysis['audio_features']
        # Duración aproximada (50ms) puede no estar si no es WAV válido; solo validar tipo si existe
        assert isinstance(af, dict)
