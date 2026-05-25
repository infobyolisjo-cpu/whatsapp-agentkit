# agent/brain.py — Cerebro del agente: conexión con Claude API
# Generado por AgentKit

"""
Lógica de IA del agente. Lee el system prompt de prompts.yaml
y genera respuestas usando la API de Anthropic Claude.
"""

import os
import yaml
import logging
import httpx
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

# Cliente de Anthropic
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# URL del workflow RAG en n8n
RAG_WEBHOOK_URL = os.getenv("RAG_WEBHOOK_URL", "")


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    """Lee el system prompt desde config/prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres un asistente útil. Responde en español.")


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos.")


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


RESPUESTA_CONTACTO = """Claro 😊 Puedes escribirnos directamente a:

📩 contacto@byolisjo.com
🌐 https://byolisjo.com

En ByOlisJo ayudamos a negocios a detectar fugas financieras, problemas operativos y áreas que frenan el crecimiento.

¿Tu consulta es sobre costos, procesos o ventas?"""

PALABRAS_CONTACTO = [
    "correo", "email", "e-mail", "contacto", "contactar", "comunicarme",
    "comunicarse", "escribirles", "escribirte", "escribirnos", "número",
    "numero", "whatsapp", "teléfono", "telefono", "celular", "cómo los contacto",
    "como los contacto", "cómo contactarlos", "como contactarlos",
    "cómo me comunico", "como me comunico", "información de contacto",
    "informacion de contacto", "datos de contacto",
]


def es_pregunta_de_contacto(mensaje: str) -> bool:
    """Detecta si el mensaje pide datos de contacto."""
    texto = mensaje.lower().strip()
    return any(palabra in texto for palabra in PALABRAS_CONTACTO)


async def consultar_rag(mensaje: str, telefono: str = "") -> str:
    """
    Consulta el workflow RAG de n8n y retorna el contexto relevante.
    Si falla o no hay URL configurada, retorna string vacío (no bloquea el flujo).
    """
    if not RAG_WEBHOOK_URL:
        return ""
    try:
        async with httpx.AsyncClient(timeout=8) as client_http:
            r = await client_http.post(
                RAG_WEBHOOK_URL,
                json={"message": mensaje, "phone": telefono},
            )
            if r.status_code == 200:
                data = r.json()
                # Acepta respuesta como {"context": "..."} o {"output": "..."} o texto directo
                if isinstance(data, dict):
                    contexto = data.get("context") or data.get("output") or data.get("text") or data.get("response") or ""
                elif isinstance(data, str):
                    contexto = data
                else:
                    contexto = ""
                if contexto:
                    logger.info(f"[RAG] Contexto obtenido ({len(contexto)} chars)")
                return contexto
            else:
                logger.warning(f"[RAG] Respuesta inesperada: {r.status_code}")
                return ""
    except Exception as e:
        logger.warning(f"[RAG] No disponible, continuando sin contexto: {e}")
        return ""


async def generar_respuesta(mensaje: str, historial: list[dict], telefono: str = "") -> str:
    """
    Genera una respuesta usando Claude API.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]

    Returns:
        La respuesta generada por Claude
    """
    # Si el mensaje es muy corto o vacío, usar fallback
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    # Interceptar preguntas de contacto — respuesta garantizada sin llamar a Claude
    if es_pregunta_de_contacto(mensaje):
        logger.info(f"Interceptado: pregunta de contacto — '{mensaje}'")
        return RESPUESTA_CONTACTO

    system_prompt = cargar_system_prompt()

    # Consultar RAG en n8n para obtener contexto específico de ByOlisJo
    contexto_rag = await consultar_rag(mensaje, telefono)

    # Si el RAG devolvió contexto, inyectarlo en el system prompt
    if contexto_rag:
        system_prompt = (
            system_prompt
            + "\n\n## Contexto relevante de la base de conocimiento ByOlisJo\n"
            + "Usa esta información para responder con más precisión:\n\n"
            + contexto_rag
        )

    # Construir mensajes para la API
    mensajes = []
    for msg in historial:
        mensajes.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    # Agregar el mensaje actual
    mensajes.append({
        "role": "user",
        "content": mensaje
    })

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=mensajes
        )

        respuesta = response.content[0].text
        logger.info(f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")
        return respuesta

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
