"""Motor de alertas y recomendaciones.

Este módulo ofrece funciones utilizadas por main.py:
 - get_child_alerts(session, child_id)
 - get_child_recommendations(session, child_id)
 - analyze_response_for_alerts(session, response_obj, analysis_dict)

La implementación aquí es ligera; la lógica avanzada vive en alert_rules.evaluate_auto_alerts
para mantener separación entre reglas y agregación de consultas.
"""
from __future__ import annotations

from typing import List, Dict
from sqlalchemy import select, func

from .models import Alert, Response, Child


def get_child_alerts(session, child_id: int) -> List[Alert]:  # pragma: no cover - passthrough simple
	return session.exec(
		select(Alert).where(Alert.child_id == child_id).order_by(Alert.created_at.desc()).limit(100)
	).all()


def get_child_recommendations(session, child_id: int) -> List[Dict]:
	"""Stub de recomendaciones derivadas de últimas emociones.

	Estrategia muy básica: mirar emoción primaria más frecuente en últimas N respuestas
	y devolver recomendación textual. En el futuro se complementará con IA.
	"""
	rows = session.exec(
		select(Response).where(Response.child_id == child_id).order_by(Response.created_at.desc()).limit(25)
	).all()
	counts = {}
	for r in rows:
		em = (r.analysis_json or {}).get("primary_emotion") or r.emotion or "Neutral"
		counts[em] = counts.get(em, 0) + 1
	if not counts:
		return []
	dominant = max(counts, key=counts.get)
	rec_map = {
		"Triste": "Animar una actividad creativa supervisada (dibujo, música suave).",
		"Enojado": "Practicar respiraciones profundas de 5 ciclos con acompañamiento adulto.",
		"Ansioso": "Proponer pausa guiada con cuento corto relajante.",
		"Mixto": "Conversación breve para clarificar sentimientos y validar emociones.",
		"Neutral": "Refuerzo positivo ligero (elogiar compartir sus emociones).",
	}
	recommendation = rec_map.get(dominant, "Tiempo de calidad y escucha activa de un adulto.")
	return [
		{
			"type": "emotion_based",
			"source_emotion": dominant,
			"recommendation": recommendation,
		}
	]


def analyze_response_for_alerts(session, response: Response, analysis: dict) -> List[Alert]:
	"""Compatibilidad con main.py; la lógica principal ya se ejecuta en Celery.

	Aquí podríamos recalcular agregados si se llama en flujo síncrono. Por ahora retorna
	la lista de alertas existentes recién creadas para el niño tras esta respuesta.
	"""
	# Retornar últimas 5 alertas para contexto
	return session.exec(
		select(Alert).where(Alert.child_id == response.child_id).order_by(Alert.created_at.desc()).limit(5)
	).all()


__all__ = [
	"get_child_alerts",
	"get_child_recommendations",
	"analyze_response_for_alerts",
]
