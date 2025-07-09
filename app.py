import logging
from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timedelta
import re
from collections import defaultdict

# Configuración avanzada de logging\LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
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

# Catálogo de productos Museballer
CATALOGO = [
    {
        "nombre": "Camiseta Museballer Edición Baloncesto",
        "precio": "$29.990",
        "descripcion": "Camiseta de algodón transpirable con diseño inspirado en el baloncesto urbano.",
        "caracteristicas": [
            "Algodón 100%",
            "Tallas S, M, L, XL",
            "Costuras reforzadas",
            "Diseño unisex"
        ]
    },
    {
        "nombre": "Sudadera Museballer con Capucha",
        "precio": "$49.990",
        "descripcion": "Sudadera cómoda con capucha ajustable y bolsillo canguro.",
        "caracteristicas": [
            "Mezcla de algodón y poliéster",
            "Capucha con cordones",
            "Bolsillo frontal",
            "Manga raglán"
        ]
    },
    {
        "nombre": "Pantalón Deportivo Museballer",
        "precio": "$39.990",
        "descripcion": "Pantalón de jogging para entrenamiento y estilo urbano.",
        "caracteristicas": [
            "Cintura elástica con cordón",
            "Bolsillos laterales con cierre",
            "Tobillos ajustados",
            "Tejido elástico"
        ]
    },
    {
        "nombre": "Gorra Museballer Snapback",
        "precio": "$19.990",
        "descripcion": "Gorra ajustable con visera plana y bordado del logo Museballer.",
        "caracteristicas": [
            "Material poliéster",
            "Correa ajustable",
            "Bordado frontal",
            "Visera plana"
        ]
    }
]

# FAQs para Museballer
FAQ = {
    "envios": (
        "Realizamos envíos a todo Chile. Una vez confirmado el pago, despachamos en un plazo máximo de 2 días hábiles. "
        "No contamos con tienda física, pero puedes coordinar retiro presencial en Santiago previo acuerdo."
    ),
    "garantia": (
        "Todas las prendas cuentan con garantía de 3 meses por defectos de fabricación. "
        "Permite cambio o devolución según corresponda."
    ),
    "pago": (
        "Aceptamos tarjetas de crédito/débito, transferencia bancaria y Mercado Pago. "
        "El procesamiento inicia tras la confirmación del pago."
    ),
    "tallas": (
        "Ofrecemos guía de tallas en nuestro sitio web para asegurar un ajuste perfecto. "
        "Si tienes dudas, contáctanos antes de comprar."
    ),
    "devoluciones": (
        "Tienes hasta 14 días para solicitar cambio o devolución gratuita. "
        "El producto debe estar sin uso y con etiqueta original."
    ),
    "contacto": (
        "Escríbenos por correo: contacto@museballer.cl\n"
        "WhatsApp: +56989419620\n"
        "Instagram: mensaje directo en https://www.instagram.com/museballer.cl\n"
        f"Tu opinión: https://tally.so/r/3xbRxo\n"
        "Visita nuestra tienda online: https://www.museballer.cl"
    )
}

# Generar prompt para el modelo
def generar_prompt_catalogo():
    productos = "\n".join([
        f"- {p['nombre']}: {p['precio']} – {p['descripcion']}"
        for p in CATALOGO
    ])
    prompt = f'''
Eres un asistente conciso y claro de Museballer.cl. Responde con frases breves, sin saltos de línea innecesarios.
Usa <strong> solo si es necesario, sin salto de línea luego de etiquetas HTML.

Catálogo:
{productos}

FAQs:
- Envíos: {FAQ['envios']}
- Garantía: {FAQ['garantia']}
- Pago: {FAQ['pago']}
- Tallas: {FAQ['tallas']}
- Devoluciones: {FAQ['devoluciones']}
- Contacto: {FAQ['contacto']}

Si no sabes la respuesta, sugiere contactar al equipo humano. Responde de forma breve y útil.
'''   
    return prompt

# Limpiar entradas inseguras
def sanitize_input(text):
    if not text:
        return ""
    sanitized = re.sub(r'[<>"'"\\]', '', text)
    return sanitized[:500]

@app.route("/")
def home():
    return '''
    <h1>API Chatbot Museballer.cl</h1>
    <p>Realiza un POST a <code>/chat</code> con JSON que incluya <code>{"message":"tu pregunta"}</code></p>
    <p>Ejemplo:<br>
    curl -X POST http://localhost:5000/chat -H "Content-Type: application/json" -d '{"message":"¿Qué prenda me recomiendas?"}'
    </p>
    <p>Para reiniciar conversación: POST /reset con JSON <code>{"session_id":"tu_sesion"}</code></p>
    '''

@app.route("/health")
def health_check():
    return jsonify({
        "status": "OK",
        "timestamp": datetime.now().isoformat(),
        "service": "Museballer Chatbot API",
        "sessions": len(conversation_history)
    }), 200

# Historial y actividad de sesiones
conversation_history = defaultdict(list)
session_activity = {}

# Eliminar sesiones expiradas
def clean_expired_sessions():
    now = datetime.now()
    expired = [sid for sid, last in session_activity.items() if now - last > SESSION_TIMEOUT]
    for sid in expired:
        conversation_history.pop(sid, None)
        session_activity.pop(sid, None)
        logger.info(f"Sesión expirada eliminada: {sid}")

@app.route("/reset", methods=["POST"])
def reset_chat():
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Falta session_id"}), 400
    conversation_history.pop(session_id, None)
    session_activity.pop(session_id, None)
    logger.info(f"Sesión reiniciada: {session_id}")
    return jsonify({"status": "Sesión reiniciada", "session_id": session_id})

@app.route("/chat", methods=["POST"])
def chat():
    clean_expired_sessions()
    logger.info("Petición /chat recibida")
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    data = request.get_json(force=True, silent=True)
    if not data or 'message' not in data:
        return jsonify({"error": "JSON inválido o falta campo 'message'"}), 400
    user_input = sanitize_input(data['message'])
    if len(user_input) < 2:
        return jsonify({"error": "Mensaje demasiado corto"}), 400
    raw_session = data.get('session_id', 'default_' + re.sub(r'\W+', '', client_ip))
    session_id = re.sub(r'\W+', '', raw_session)[:64] or 'default_session'
    session_activity[session_id] = datetime.now()
    if session_id not in conversation_history:
        conversation_history[session_id].append({
            'role': 'system',
            'content': generar_prompt_catalogo()
        })
        logger.info(f"Nueva sesión iniciada: {session_id}")
    conversation_history[session_id].append({'role': 'user', 'content': user_input})
    try:
        start = datetime.now()
        res = requests.post(
            "https://api.kluster.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {KLUSTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": conversation_history[session_id], "max_tokens": 250, "temperature": 0.5},
            timeout=15
        )
        res.raise_for_status()
        resp_time = (datetime.now() - start).total_seconds()
        logger.info(f"Respuesta Kluster en {resp_time:.2f}s")
        result = res.json()
        reply = result['choices'][0]['message']['content'].replace('\n', ' ').strip()
        conversation_history[session_id].append({'role': 'assistant', 'content': reply})
        if len(conversation_history[session_id]) > 9:
            conversation_history[session_id] = [conversation_history[session_id][0]] + conversation_history[session_id][-8:]
        return jsonify({'reply': reply, 'session_id': session_id})
    except Exception as e:
        logger.error(f"Error al procesar chat: {e}")
        return jsonify({"error": "Error interno", "details": str(e)}), 500

# CORS
ALLOWED_ORIGINS = [
    "https://www.museballer.cl",
    "https://museballer.cl"
]
@app.after_request
 def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET'
    return response

@app.route("/chat", methods=["OPTIONS"])
def handle_options():
    return jsonify({}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
