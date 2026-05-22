#!/bin/bash

echo ""
echo "======================================="
echo "   ByOlisJo — Iniciando servidor..."
echo "======================================="
echo ""

# Instalar dependencias si faltan
pip3 install fastapi uvicorn httpx sqlalchemy aiosqlite python-dotenv \
  python-multipart pyyaml anthropic --break-system-packages -q 2>/dev/null

# Verificar .env
if [ ! -f .env ]; then
  echo "⚠️  No se encontró .env — copiando desde .env.example"
  cp .env.example .env
fi

echo "✅ Dependencias OK"
echo "✅ Servidor en http://localhost:8000"
echo "✅ Webhook en http://localhost:8000/webhook"
echo ""
echo "Presiona Ctrl+C para detener."
echo ""

uvicorn agent.main:app --reload --port 8000
