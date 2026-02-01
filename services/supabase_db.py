import os
import streamlit as st
from supabase import create_client, Client
from datetime import datetime
import time

# --- CONFIGURACIÓN DE CLIENTES ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
service_key: str = os.environ.get("SUPABASE_SERVICE_KEY")

# 1. Cliente Público (Para lecturas generales o auth)
supabase: Client = create_client(url, key)

# 2. Cliente Admin (Para escrituras privilegiadas o bypass de RLS)
# IMPORTANTE: Asegúrate de tener SUPABASE_SERVICE_KEY en tus .env o secrets de Streamlit
if service_key:
    supabase_admin_client: Client = create_client(url, service_key)
else:
    supabase_admin_client = None


# --- FUNCIONES EXISTENTES (Mantenlas igual, solo resumo para contexto) ---

def log_query_event(query_text, mode="general", tokens=0):
    try:
        if "user" in st.session_state and st.session_state.user:
            user_data = st.session_state.user
            email = user_data.email if hasattr(user_data, 'email') else "unknown"
            
            data = {
                "user_name": email,
                "query": query_text,
                "mode": mode,
                "total_tokens": tokens,
                "timestamp": datetime.now().isoformat()
            }
            supabase.table("queries").insert(data).execute()
    except Exception as e:
        print(f"Error logging query: {e}")

def get_daily_usage(user, mode):
    # (Tu código existente de get_daily_usage...)
    try:
        if not user: return 0
        email = user.email
        start_of_day = datetime.now().strftime("%Y-%m-%dT00:00:00")
        
        response = supabase.table("queries") \
            .select("id", count='exact') \
            .eq("user_name", email) \
            .eq("mode", mode) \
            .gte("timestamp", start_of_day) \
            .execute()
        return response.count
    except:
        return 0

# ==============================
# CORRECCIÓN: REGISTRO DE FEEDBACK (USANDO ADMIN)
# ==============================
def log_message_feedback(content: str, mode: str, vote_type: str):
    """
    Registra un voto usando el cliente ADMIN para evitar bloqueos por RLS.
    """
    # 1. Validación de Usuario
    if "user" not in st.session_state or not st.session_state.user:
        print("Feedback Error: No user in session")
        return False 

    # 2. Validación de Cliente Admin
    if not supabase_admin_client:
        st.error("Error de configuración: Falta SUPABASE_SERVICE_KEY para guardar feedback.")
        return False

    try:
        user_id = st.session_state.user.id
        
        # Recortar contenido para no saturar DB
        short_content = content[:500] + "..." if len(content) > 500 else content

        data = {
            "user_id": user_id,
            "mode": mode,
            "message_content": short_content,
            "vote_type": vote_type
        }

        # USAMOS EL CLIENTE ADMIN AQUÍ:
        response = supabase_admin_client.table("message_feedback").insert(data).execute()
        
        # Verificamos si hubo respuesta de datos
        if response.data:
            return True
        return False

    except Exception as e:
        # Esto imprimirá el error real en tu terminal/consola de Streamlit Cloud
        print(f"❌ Error CRÍTICO guardando feedback: {e}")
        # Opcional: Mostrar error en pantalla para debug (bórralo después)
        # st.error(f"Error DB: {e}")
        return False

# ==============================
# FUNCIÓN RECUPERADA: USO MENSUAL
# ==============================
def get_monthly_usage(user, mode):
    try:
        if not user: return 0
        email = user.email
        # Calcular el primer día del mes actual
        start_of_month = datetime.now().replace(day=1).strftime("%Y-%m-%dT00:00:00")
        
        response = supabase.table("queries") \
            .select("id", count='exact') \
            .eq("user_name", email) \
            .eq("mode", mode) \
            .gte("timestamp", start_of_month) \
            .execute()
        return response.count
    except:
        return 0
