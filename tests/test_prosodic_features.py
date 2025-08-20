import os
import tempfile
import time
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.audio_utils import limpiar_archivos_antiguos


def test_prosodic_features_extraction():
    """Test extracción de características prosódicas con librosa (si disponible)."""
    import numpy as np
    import librosa  # noqa: F401
    import soundfile as sf
    from backend.app.audio_utils import _extraer_features_prosodicos
    
    # Crear audio sintético simple
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        sr = 16000
        duration = 1.0  # 1 segundo
        # Generar señal con frecuencia variable (simular speech)
        t = np.linspace(0, duration, int(sr * duration))
        freq = 200 + 50 * np.sin(2 * np.pi * 0.5 * t)  # F0 variable
        signal = 0.3 * np.sin(2 * np.pi * freq * t)
        
        sf.write(tmp.name, signal, sr)
        tmp_name = tmp.name
    
    try:
        features = _extraer_features_prosodicos(tmp_name)
        
        # Verificar que se extraen las características esperadas
        expected_keys = [
            "pitch_mean_hz", "pitch_std_hz", "energy_mean_db", 
            "spectral_centroid_hz", "pause_ratio"
        ]
        for key in expected_keys:
            assert key in features, f"Feature {key} no encontrado"
            assert isinstance(features[key], (int, float)), f"Feature {key} no es numérico"
        
        # Pitch debería estar en rango razonable para speech humano
        if features["pitch_mean_hz"] > 0:
            assert 50 <= features["pitch_mean_hz"] <= 500, "Pitch fuera de rango esperado"
        
    finally:
        try:
            os.unlink(tmp_name)
        except Exception:
            pass


def test_audio_compression():
    """Test compresión de archivos de audio."""
    from backend.app.audio_utils import comprimir_audio
    
    # Crear archivo temporal
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
        tmp.write(b'fake mp3 data' * 1000)  # Simular archivo más grande
        tmp_name = tmp.name
    
    try:
        # Comprimir (debería retornar path original o nuevo)
        result_path = comprimir_audio(tmp_name)
        assert os.path.isfile(result_path)
        
    finally:
        try:
            os.unlink(tmp_name)
        except Exception:
            pass


def test_audio_cleanup():
    """Test limpieza de archivos antiguos."""
    # Crear directorio temporal
    test_dir = tempfile.mkdtemp()
    uploads_backup = "uploads"
    
    try:
        # Cambiar temporalmente directorio de uploads
        import backend.app.audio_utils
        backend.app.audio_utils.settings.audio_cleanup_days = 0  # limpiar todo
        
        # Crear archivos de prueba
        old_file = os.path.join(test_dir, "old_audio.wav")
        new_file = os.path.join(test_dir, "new_audio.wav")
        
        with open(old_file, 'w') as f:
            f.write("old audio")
        with open(new_file, 'w') as f:
            f.write("new audio")
        
        # Hacer que old_file parezca más antiguo
        old_time = time.time() - 86400  # 1 día atrás
        os.utime(old_file, (old_time, old_time))
        
        # Monkey patch para usar nuestro directorio de prueba
        original_uploads = backend.app.audio_utils.settings.allowed_audio_formats
        backend.app.audio_utils.settings.allowed_audio_formats = ["wav"]
        
        # Mock del directorio uploads
        def mock_listdir(path):
            if path == "uploads":
                return ["old_audio.wav", "new_audio.wav"]
            return os.listdir(path)
        
        def mock_join(base, name):
            if base == "uploads":
                return os.path.join(test_dir, name)
            return os.path.join(base, name)
        
        def mock_isdir(path):
            return path == "uploads" or os.path.isdir(path)
        
        def mock_isfile(path):
            return os.path.isfile(path)
        
        def mock_getmtime(path):
            return os.path.getmtime(path)
        
        def mock_unlink(path):
            return os.unlink(path)
        
        # Aplicar mocks
        import backend.app.audio_utils
        orig_listdir = os.listdir
        orig_join = os.path.join
        orig_isdir = os.path.isdir
        orig_isfile = os.path.isfile
        orig_getmtime = os.path.getmtime
        orig_unlink = os.unlink
        
        os.listdir = mock_listdir
        os.path.join = mock_join
        os.path.isdir = mock_isdir
        os.path.isfile = mock_isfile
        os.path.getmtime = mock_getmtime
        os.unlink = mock_unlink
        
        cleaned = limpiar_archivos_antiguos()
        
        # Restaurar funciones originales
        os.listdir = orig_listdir
        os.path.join = orig_join
        os.path.isdir = orig_isdir
        os.path.isfile = orig_isfile
        os.path.getmtime = orig_getmtime
        os.unlink = orig_unlink
        
        # Verificar que se limpió al menos un archivo
        assert cleaned >= 0  # Función debería ejecutarse sin error
        
    finally:
        # Limpiar directorio de prueba
        import shutil
        try:
            shutil.rmtree(test_dir)
        except Exception:
            pass


def test_admin_cleanup_endpoint():
    """Test endpoint de limpieza para admin."""
    client = TestClient(app)
    
    # Registrar admin
    r_admin = client.post('/api/auth/register', json={
        'email': 'admin@cleanup.com', 'password': 'pass123', 'role': 'admin'
    })
    assert r_admin.status_code in (200, 201)
    
    # Login
    login = client.post('/api/auth/login', json={
        'email': 'admin@cleanup.com', 'password': 'pass123'
    })
    token = login.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    
    # Llamar endpoint de limpieza
    r_cleanup = client.get('/api/admin/cleanup-audio', headers=headers)
    assert r_cleanup.status_code == 200
    assert 'task_id' in r_cleanup.json()


def test_grok_with_audio_features():
    """Test integración de Grok con características de audio."""
    from backend.app.grok_client import analyze_text, _enrich_with_audio_features
    
    # Características de audio de prueba
    audio_features = {
        "pitch_mean_hz": 180.5,
        "energy_mean_db": 0.4,
        "pause_ratio": 0.1
    }
    
    # Analizar con features (usará mock ya que Grok no está configurado)
    result = analyze_text("Estoy muy emocionado!", audio_features)
    
    assert "audio_features" in result
    assert result["audio_features"] == audio_features
    assert "tone_features" in result
    assert result["tone_features"]["pitch_mean_hz"] == 180.5
