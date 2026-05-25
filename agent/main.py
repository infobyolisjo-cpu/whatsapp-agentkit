# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit para ByOlisJo AI Assistant

"""
Servidor principal del agente OlisJo AI.
Funciona con cualquier proveedor (Whapi, Meta, Twilio) gracias a la capa de providers.
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor

load_dotenv()

# Configuración de logging según entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

# Proveedor de WhatsApp (se configura en .env con WHATSAPP_PROVIDER)
proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

CRM_WEBHOOK_URL = os.getenv("CRM_WEBHOOK_URL", "")
CRM_WEBHOOK_SECRET = os.getenv("CRM_WEBHOOK_SECRET", "")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")


async def notificar_crm(telefono: str, texto: str) -> None:
    """
    Envía el nuevo contacto de WhatsApp al CRM (fire & forget).
    Solo se llama en el primer mensaje — historial vacío indica contacto nuevo.
    """
    if not CRM_WEBHOOK_URL:
        return
    payload = {
        "name": f"WhatsApp {telefono}",
        "phone": telefono,
        "source": "whatsapp",
        "channel": "whatsapp",
        "notes": texto[:500],  # limitar notas a 500 chars
    }
    headers = {"Content-Type": "application/json"}
    if CRM_WEBHOOK_SECRET:
        headers["x-webhook-secret"] = CRM_WEBHOOK_SECRET
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(CRM_WEBHOOK_URL, json=payload, headers=headers)
            if r.status_code == 201:
                logger.info(f"[CRM] Lead creado: {telefono}")
            else:
                logger.warning(f"[CRM] Respuesta inesperada {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"[CRM] Error al notificar: {e}")


async def notificar_n8n(telefono: str, texto: str) -> None:
    """
    Notifica a n8n cada vez que un cliente envía un mensaje.
    Fire-and-forget: nunca interrumpe la conversación si falla.
    """
    if not N8N_WEBHOOK_URL:
        return
    payload = {
        "phone": telefono,
        "message": texto,
        "name": f"WhatsApp {telefono}",
        "source": "whatsapp_agentkit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(N8N_WEBHOOK_URL, json=payload)
            if r.status_code == 200:
                logger.info(f"[n8n] Notificación enviada OK: {telefono}")
            else:
                logger.warning(f"[n8n] Respuesta inesperada {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"[n8n] Error al notificar (no afecta WhatsApp): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="OlisJo AI — ByOlisJo AI Assistant",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    return {"status": "ok"}


@app.api_route("/webhook", methods=["GET", "HEAD"])
async def webhook_verificacion(request: Request):
    hub_mode = request.query_params.get("hub.mode")
    hub_verify_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")

    verify_token = os.getenv("VERIFY_TOKEN")

    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return PlainTextResponse(content=str(hub_challenge))

    return PlainTextResponse(content="Error", status_code=403)


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp via el proveedor configurado.
    Procesa el mensaje, genera respuesta con Claude y la envía de vuelta.
    """
    try:
        # Parsear webhook — el proveedor normaliza el formato
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            # Ignorar mensajes propios o vacíos
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            # Obtener historial ANTES de guardar el mensaje actual
            historial = await obtener_historial(msg.telefono)

            # Notificar CRM si es el primer mensaje de este número (contacto nuevo)
            if not historial:
                asyncio.create_task(notificar_crm(msg.telefono, msg.texto))

            # Generar respuesta con Claude + contexto RAG de n8n
            respuesta = await generar_respuesta(msg.texto, historial, telefono=msg.telefono)

            # Guardar mensaje del usuario Y respuesta del agente en memoria
            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            # Notificar n8n con cada mensaje del cliente (fire & forget)
            asyncio.create_task(notificar_n8n(msg.telefono, msg.texto))

            # Enviar respuesta por WhatsApp via el proveedor
            await proveedor.enviar_mensaje(msg.telefono, respuesta)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.responses import HTMLResponse
import sqlite3

@app.get("/inbox", response_class=HTMLResponse)
async def ver_inbox():
    html = """
    <html>
    <head>
    <style>
        body {
            font-family: Arial;
            background: white;
            padding: 20px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            background: #f4f4f4;
            text-align: left;
            padding: 10px;
            font-size: 14px;
        }
        td {
            padding: 10px;
            border-bottom: 1px solid #ddd;
            font-size: 14px;
        }
        .user { color: #000; }
        .bot { color: #555; }
    </style>
    </head>
    <body>

    <h2>📊 Inbox ByOlisJo</h2>

    <table>
        <tr>
            <th>Número</th>
            <th>Tipo</th>
            <th>Mensaje</th>
        </tr>
    """

    try:
        conn = sqlite3.connect("agentkit.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT telefono, role, content FROM mensajes ORDER BY id DESC LIMIT 100"
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            html += "<tr><td colspan='3'>No hay conversaciones aún</td></tr>"
        else:
            for telefono, role, content in rows:
                clase = "user" if role == "user" else "bot"
                tipo = "Cliente" if role == "user" else "Bot"

                html += f"""
                <tr>
                    <td>{telefono}</td>
                    <td>{tipo}</td>
                    <td class="{clase}">{content}</td>
                </tr>
                """

    except Exception as e:
        html += f"<tr><td colspan='3'>Error: {str(e)}</td></tr>"

    html += "</table></body></html>"

    return html
