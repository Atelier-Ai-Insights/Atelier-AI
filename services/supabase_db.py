import streamlit as st
import datetime
from supabase import create_client, Client

# ==============================
# CONEXIÓN A SUPABASE
# ==============================
supabase: Client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase_admin_client: Client | None = None
if "SUPABASE_SERVICE_KEY" in st.secrets:
    supabase_admin_client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])

# ==============================
# RASTREO DE USO
# ==============================

def log_query_event(query_text, mode, rating=None):
    """
    Registra una consulta y DEVUELVE el ID de la fila creada.
    """
    try:
        data = {
            "id": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S%f"),
            "user_name": st.session_state.user,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mode": mode,
            "query": query_text,
            "rating": rating
        }
        
        # --- ¡CAMBIO AQUÍ! ---
        # Usamos .select() para que Supabase nos devuelva los datos insertados
        response = supabase.table("queries").insert(data).select("id").execute()
        
        if response.data:
            return response.data[0]['id'] # Devuelve el ID de la nueva consulta
        # --- FIN DEL CAMBIO ---
        
    except Exception as e: 
        print(f"Error log query: {e}")
    return None # Devuelve None si falla

# --- ¡NUEVA FUNCIÓN AÑADIDA! ---
def log_query_feedback(query_id, rating_value):
    """
    Actualiza una consulta existente con el feedback (1 para like, 0 para dislike).
    """
    try:
        supabase.table("queries").update({"rating": rating_value}).eq("id", query_id).execute()
        return True
    except Exception as e:
        print(f"Error logging feedback: {e}")
        return False
# --- FIN DE LA NUEVA FUNCIÓN ---

def get_monthly_usage(username, action_type):
    # ... (esta función no cambia)
    try: 
        first_day_iso = datetime.date.today().replace(day=1).isoformat()
        response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", first_day_iso).execute()
        return response.count
    except Exception as e: print(f"Error get monthly usage: {e}"); return 0

def get_daily_usage(username, action_type):
    # ... (esta función no cambia)
    try: 
        today_start_iso = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        response = supabase.table("queries").select("id", count='exact').eq("user_name", username).eq("mode", action_type).gte("timestamp", today_start_iso).execute()
        return response.count
    except Exception as e: print(f"Error get daily usage: {e}"); return 0