import streamlit as st
import datetime
import os
from supabase import create_client, Client

# ==============================
# FUNCIÓN SEGURA PARA OBTENER SECRETOS
# ==============================
def get_secret(key):
    # 1. Intenta leer de las variables de entorno (Railway/Producción)
    value = os.environ.get(key)
    # 2. Si no existe, intenta leer de secrets.toml (Local/Streamlit Cloud)
    if not value:
        try:
            value = st.secrets.get(key)
        except:
            return None
    return value

# ==============================
# CONEXIÓN A SUPABASE
# ==============================
# Usamos la función segura en lugar de llamar directamente a st.secrets
supabase_url = get_secret("SUPABASE_URL")
supabase_key = get_secret("SUPABASE_KEY")
service_key = get_secret("SUPABASE_SERVICE_KEY")

# Validación básica para evitar errores feos si faltan las claves
if not supabase_url or not supabase_key:
    # Esto evita que la app explote, pero avisa si faltan datos
    print("⚠️ ADVERTENCIA: No se encontraron las credenciales de Supabase.")
    # Creamos un cliente dummy o detenemos la ejecución si es crítico
    # Para este caso, dejamos que falle controladamente si se intenta usar
    supabase: Client = None 
else:
    supabase: Client = create_client(supabase_url, supabase_key)

supabase_admin_client: Client | None = None
if service_key and supabase_url:
    supabase_admin_client = create_client(supabase_url, service_key)

# ==============================
# RASTREO DE USO
# ==============================

def log_query_event(query_text, mode, rating=None):
    """
    Registra una consulta en la base de datos, incluyendo costos de tokens.
    """
    # Si supabase no cargó por falta de claves, salimos para no romper la app
    if not supabase:
        print("Supabase no conectado, saltando log.")
        return

    try:
        generated_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S%f")
        
        # --- RECUPERAR TOKENS DE LA SESIÓN (GUARDADOS POR GEMINI_API) ---
        token_data = st.session_state.get("last_token_usage", {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0})
        
        data = {
            "id": generated_id,
            "user_name": st.session_state.user,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mode": mode,
            "query": query_text,
            "rating": None,
            
            # --- COLUMNAS DE COSTOS ---
            "tokens_input": token_data.get("prompt_tokens", 0),
            "tokens_output": token_data.get("candidates_tokens", 0),
            "total_tokens": token_data.get("total_tokens", 0)
        }
        
        supabase.table("queries").insert(data).execute()
        
        # Limpiar para la próxima
        st.session_state.last_token_usage = {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0}
        
    except Exception as e: 
        print(f"Error log query: {e}")

def get_monthly_usage(username, action_type):
    if not supabase: return 0
    try: 
        first_day_iso = datetime.date.today().replace(day=1).isoformat()
        response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", first_day_iso).execute()
        return response.count
    except Exception as e: print(f"Error get monthly usage: {e}"); return 0

def get_daily_usage(username, action_type):
    if not supabase: return 0
    try: 
        today_start_iso = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", today_start_iso).execute()
        return response.count
    except Exception as e: print(f"Error get daily usage: {e}"); return 0

# ==============================
# NUEVA FUNCIÓN: REGISTRO DE FEEDBACK
# ==============================
def log_message_feedback(content: str, mode: str, vote_type: str):
    """
    Registra un voto positivo (up) o negativo (down) para un mensaje.
    """
    try:
        if "user" not in st.session_state or not st.session_state.user:
            return False # No hay usuario logueado

        user_id = st.session_state.user.id
        
        # Guardamos solo los primeros 200 caracteres para contexto, ahorrar espacio
        short_content = content[:200] + "..." if len(content) > 200 else content

        data = {
            "user_id": user_id,
            "mode": mode,
            "message_content": short_content,
            "vote_type": vote_type
        }

        supabase.table("message_feedback").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error logging feedback: {e}")
        return False
