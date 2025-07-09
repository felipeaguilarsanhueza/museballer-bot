""import logging
from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timedelta
import re
from collections import defaultdict

# Configuración avanzada de logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logger.info("Iniciando aplicación Flask")

app = Flask(__name__)

# Clave de Kluster desde variables de entorno
KLUSTER_API_KEY = os.getenv("KLUSTER_API_KEY", "06a53bbf-ee89-4694-a28f-83a739f540ed")
MODEL = "deepseek-ai/DeepSeek-V3-0324"

# Configuración de sesiones
SESSION_TIMEOUT = timedelta(minutes=30)  # Tiempo de expiración de sesiones

# Catálogo Museballer (simplificado)
CATALOGO = [
    {
        "nombre": "Cortaviento Negro/Azul",
        "precio": "$39.990 CLP",
        "descripcion": "Cortaviento urbano resistente al viento. Color Negro con Azul Cielo. Disponible en tallas M y L.",
        "caracteristicas": [
            "Tela ligera y durable",
            "Diseño urbano con cierre frontal",
            "Capucha ajustable",
            "Bolsillos funcionales",
            "Logotipo Museballer bordado"
        ]
    },
    {
        "nombre": "Hoodie Naranjo",
        "precio": "$34.990 CLP",
        "descripcion": "Polerón oversize en color naranjo vibrante. Interior afelpado y capucha con cordones.",
        "caracteristicas": [
            "Algodón suave con interior térmico",
            "Estilo oversize unisex",
            "Disponible en tallas M y L",
            "Logotipo Museballer serigrafiado",
            "Puños y cintura elasticados"
        ]
    }
]

FAQ = {
    "envios": (
        "Realizamos envíos a todo Chile mediante courier. El despacho se realiza dentro de 48 horas hábiles una vez confirmado el pago."
    ),
    "garantia": (
        "Todos nuestros productos cuentan con garantía legal por 6 meses desde la fecha de compra."
    ),
    "pago": (
        "Aceptamos pagos por transferencia bancaria, tarjetas de débito/crédito y efectivo (solo en Santiago coordinado por WhatsApp)."
    ),
    "portabilidad": (
        "Nuestra ropa es liviana, versátil y pensada para acompañarte en la ciudad y la cancha."
    ),
    "tecnico": (
        "Para cambios o devoluciones, contáctanos por WhatsApp o Instagram dentro del plazo de garantía."
    ),
    "salud": (
        "Vestirse bien también es salud mental. Diseñamos piezas que te hagan sentir seguro/a, cómodo/a y auténtico/a."
    ),
    "contacto": (
        "- WhatsApp: +56 9 8941 9620\n"
        "- Instagram: [@museballer](https://www.instagram.com/museballer)\n"
        "- Tienda: https://www.museballer.cl\n"
        "- Opiniones: https://tally.so/r/3xbRxo"
    )
}

def generar_prompt_catalogo():
    productos = "\n".join([f"- {p['nombre']}: {p['precio']} – {p['descripcion']}" for p in CATALOGO])
    prompt = f"""
Eres un asistente conciso y claro de Museballer.cl. Responde con frases breves, sin usar saltos de línea innecesarios. 
Usa <strong> solo si es necesario, pero no agregues salto de línea luego de etiquetas HTML.

Catálogo:
{productos}

FAQs:
- Envíos: {FAQ['envios']}
- Garantía: {FAQ['garantia']}
- Pago: {FAQ['pago']}
- Portabilidad: {FAQ['portabilidad']}
- Técnico: {FAQ['tecnico']}
- Salud: {FAQ['salud']}
- Contacto: {FAQ['contacto']}

Si no sabes la respuesta, sugiere contactar al equipo humano. Responde de forma breve y útil.
"""
    return prompt

def sanitize_input(text):
    if not text:
        return ""
    sanitized = re.sub(r'[<>"\'\\]', '', text)
    return sanitized[:500]

@app.route("/")
def home():
    return """
    <h1>API Chatbot Museballer.cl</h1>
    <p>POST a /chat con JSON {"message":"tu pregunta"}</p>
    <p>Ejemplo con curl:<br>
    curl -X POST http://localhost:5000/chat -H "Content-Type: application/json" -d '{"message":"¿Qué vaporizador me recomiendas?"}'
    </p>
    <p>Para reiniciar conversación: POST /reset con JSON {"session_id":"tu_sesion"}</p>
    """

@app.route("/health")
def health_check():
    return jsonify({
        "status": "OK", 
        "timestamp": datetime.now().isoformat(), 
        "service": "Museballer Chatbot API",
        "sessions": len(conversation_history)
    }), 200

# Almacenamiento de sesiones con tiempo de última actividad
conversation_history = defaultdict(list)
session_activity = {}

# Limpiar sesiones expiradas
def clean_expired_sessions():
    now = datetime.now()
    expired = []
    for session_id, last_active in list(session_activity.items()):
        if now - last_active > SESSION_TIMEOUT:
            expired.append(session_id)
    
    for session_id in expired:
        if session_id in conversation_history:
            del conversation_history[session_id]
        if session_id in session_activity:
            del session_activity[session_id]
        logger.info(f"Sesión expirada eliminada: {session_id}")

@app.route("/reset", methods=["POST"])
def reset_chat():
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get("session_id")
    
    if not session_id:
        return jsonify({"error": "Falta session_id"}), 400
    
    if session_id in conversation_history:
        del conversation_history[session_id]
    if session_id in session_activity:
        del session_activity[session_id]
    
    logger.info(f"Sesión reiniciada: {session_id}")
    return jsonify({"status": "Sesión reiniciada", "session_id": session_id})

@app.route("/chat", methods=["POST"])
def chat():
    clean_expired_sessions()  # Limpiar sesiones antes de procesar
    
    logger.info("Petición /chat recibida")
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    logger.info(f"IP cliente: {client_ip}")

    data = request.get_json(force=True, silent=True)
    if not data or "message" not in data:
        return jsonify({"error": "JSON inválido o falta campo 'message'"}), 400

    user_input = sanitize_input(data["message"])
    if len(user_input) < 2:
        return jsonify({"error": "Mensaje demasiado corto"}), 400

    # Sanitizar y obtener session_id
    raw_session_id = data.get("session_id", "default_" + re.sub(r'\W+', '', client_ip))
    session_id = re.sub(r'\W+', '', raw_session_id)[:64] or "default_session"
    
    # Actualizar tiempo de actividad
    session_activity[session_id] = datetime.now()

    # Inicializar sesión si es nueva
    if session_id not in conversation_history:
        conversation_history[session_id].append({
            "role": "system",
            "content": generar_prompt_catalogo()
        })
        logger.info(f"Nueva sesión iniciada: {session_id}")

    # Añadir mensaje de usuario al historial
    conversation_history[session_id].append({
        "role": "user",
        "content": user_input
    })

    logger.info(f"Session: {session_id} - Mensaje: {user_input}")
    logger.debug(f"Historial actual: {conversation_history[session_id]}")

    try:
        start_time = datetime.now()
        response = requests.post(
            "https://api.kluster.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {KLUSTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": conversation_history[session_id],
                "max_tokens": 250,
                "temperature": 0.5
            },
            timeout=15
        )
        response.raise_for_status()
        response_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Respuesta Kluster en {response_time:.2f}s")

        result = response.json()
        if "choices" not in result or not result["choices"]:
            return jsonify({"error": "Respuesta inesperada del modelo"}), 500

        reply = result["choices"][0]["message"]["content"].replace('\n', ' ').strip()
        
        # Añadir respuesta al historial
        conversation_history[session_id].append({
            "role": "assistant",
            "content": reply
        })
        
        # Mantener sistema + últimos 4 intercambios (máximo 9 mensajes)
        if len(conversation_history[session_id]) > 9:
            conversation_history[session_id] = [conversation_history[session_id][0]] + conversation_history[session_id][-8:]

        logger.debug(f"Historial actualizado: {conversation_history[session_id]}")

        return jsonify({
            "reply": reply,
            "session_id": session_id  # Devolver ID para continuar conversación
        })

    except requests.exceptions.RequestException as e:
        logger.error(f"Error API Kluster: {e}")
        return jsonify({"error": "Error al conectar con la API de IA", "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return jsonify({"error": "Error interno", "details": str(e)}), 500

# CORS
ALLOWED_ORIGINS = ["https://www.museballer.cl", "https://museballer.cl", "https://bio.museballer.cl"]
@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET, DELETE'
    return response

@app.route("/chat", methods=["OPTIONS"])
def handle_options():
    return jsonify({}), 200