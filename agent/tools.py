# agent/tools.py — Herramientas del agente OlisJo AI
# Generado por AgentKit para ByOlisJo AI Assistant

"""
Herramientas específicas del negocio.
Extienden las capacidades del agente más allá de responder texto.
"""

import os
import yaml
import logging
from datetime import datetime

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención del negocio."""
    info = cargar_info_negocio()
    ahora = datetime.now()
    dia_semana = ahora.weekday()  # 0=Lunes, 6=Domingo
    hora_actual = ahora.hour

    # Horario: Lunes a Viernes 9am-6pm
    esta_abierto = (
        0 <= dia_semana <= 4 and  # Lunes a Viernes
        9 <= hora_actual < 18     # 9am a 6pm
    )

    return {
        "horario": info.get("negocio", {}).get("horario", "Lunes a Viernes 9:00 AM a 6:00 PM"),
        "esta_abierto": esta_abierto,
        "atencion_ia_24h": True,  # El agente de IA atiende 24/7
    }


def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    """
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


def registrar_lead(telefono: str, nombre: str, interes: str) -> dict:
    """
    Registra un prospecto interesado en los servicios de ByOlisJo AI Assistant.
    Guarda el lead en un archivo CSV simple para seguimiento del equipo.
    """
    import csv
    archivo_leads = "knowledge/leads.csv"
    es_nuevo = not os.path.exists(archivo_leads)

    try:
        with open(archivo_leads, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if es_nuevo:
                writer.writerow(["fecha", "telefono", "nombre", "interes"])
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                telefono,
                nombre,
                interes
            ])
        logger.info(f"Lead registrado: {telefono} — {nombre}")
        return {"registrado": True, "mensaje": "Lead guardado correctamente"}
    except Exception as e:
        logger.error(f"Error al registrar lead: {e}")
        return {"registrado": False, "mensaje": str(e)}


def calificar_lead(interes: str) -> str:
    """
    Califica el nivel de interés de un prospecto basado en su mensaje.
    Retorna: 'alto', 'medio' o 'bajo'
    """
    palabras_alto = ["quiero", "necesito", "cuánto cuesta", "precio", "contratar",
                     "empezar", "comenzar", "ya", "urgente", "pronto", "hoy"]
    palabras_medio = ["me interesa", "información", "más detalles", "cómo funciona",
                      "qué incluye", "dudas", "preguntas"]

    interes_lower = interes.lower()

    if any(p in interes_lower for p in palabras_alto):
        return "alto"
    elif any(p in interes_lower for p in palabras_medio):
        return "medio"
    else:
        return "bajo"


def escalar_a_especialista(telefono: str, contexto: str) -> str:
    """
    Genera un mensaje de escalación para que el equipo humano retome la conversación.
    En producción, esto podría enviar una notificación al equipo.
    """
    mensaje = (
        f"📋 *Escalación a especialista*\n"
        f"Cliente: {telefono}\n"
        f"Motivo: {contexto}\n"
        f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Un especialista de ByOlisJo AI Assistant se contactará contigo pronto."
    )
    logger.info(f"Escalación generada para {telefono}: {contexto}")
    return mensaje
