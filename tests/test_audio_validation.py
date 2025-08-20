import tempfile
import os
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.audio_utils import AudioValidationError, validar_audio


def test_audio_validation_size_limit():
    """Test que rechaza archivos muy grandes."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        # Crear archivo de 1MB (debería pasar con límite default de 50MB)
        tmp.write(b'0' * (1024 * 1024))
        tmp.flush()
        tmp_name = tmp.name
    
    try:
        validar_audio(tmp_name, 1024 * 1024)  # Debería pasar
    except AudioValidationError:
        assert False, "1MB debería pasar"
    
    try:
        # Simular archivo de 100MB (debería fallar)
        validar_audio(tmp_name, 100 * 1024 * 1024)
        assert False, "100MB debería fallar"
    except AudioValidationError as e:
        assert "muy grande" in str(e)
    
    finally:
        try:
            os.unlink(tmp_name)
        except Exception:
            pass


def test_audio_validation_format():
    """Test que rechaza formatos no permitidos."""
    with tempfile.NamedTemporaryFile(suffix='.xyz', delete=False) as tmp:
        tmp.write(b'fake audio data')
        tmp.flush()
        tmp_name = tmp.name
    
    try:
        validar_audio(tmp_name, 100)
        assert False, "Formato .xyz debería fallar"
    except AudioValidationError as e:
        assert "Formato no permitido" in str(e)
    finally:
        try:
            os.unlink(tmp_name)
        except Exception:
            pass


def test_audio_upload_invalid_format():
    """Test integración: subir formato inválido debe retornar 400."""
    client = TestClient(app)
    r_parent = client.post('/api/auth/register', json={'email': 'badaudio@example.com', 'password': 'pass123', 'role': 'parent'})
    assert r_parent.status_code in (200, 201)
    
    # Archivo con extensión no permitida
    files = {'audio_file': ('test.xyz', b'fake audio', 'audio/xyz')}
    r_submit = client.post('/api/submit-responses', data={'child_id': 'test', 'text': 'hola'}, files=files)
    assert r_submit.status_code == 400
    assert "Audio inválido" in r_submit.text


def test_transcription_cache_key_generation():
    """Test generación de claves de caché."""
    from backend.app.audio_utils import _get_transcription_cache_key
    
    # Crear archivo temporal pequeño
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b'test audio data')
        tmp.flush()
        tmp_name = tmp.name
    
    try:
        key1 = _get_transcription_cache_key(tmp_name, "base", "es")
        key2 = _get_transcription_cache_key(tmp_name, "base", "en")
        key3 = _get_transcription_cache_key(tmp_name, "small", "es")
        
        # Diferentes parámetros deben generar claves diferentes
        assert key1 != key2
        assert key1 != key3
        assert key2 != key3
        
        # Mismo archivo y parámetros debe generar misma clave
        key1_repeat = _get_transcription_cache_key(tmp_name, "base", "es")
        assert key1 == key1_repeat
    finally:
        try:
            os.unlink(tmp_name)
        except Exception:
            pass
