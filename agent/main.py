# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit para ByOlisJo AI Assistant

"""
Servidor principal del agente OlisJo AI.
Funciona con cualquier proveedor (Whapi, Meta, Twilio) gracias a la capa de providers.
"""

import os
import logging
from contextlib import asynccontextmanager

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

            # Generar respuesta con Claude
            respuesta = await generar_respuesta(msg.texto, historial)

            # Guardar mensaje del usuario Y respuesta del agente en memoria
            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

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
