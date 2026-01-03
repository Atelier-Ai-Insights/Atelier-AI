import streamlit as st
from datetime import datetime

# Función existente para GUARDAR (ya la tienes)
def save_project_insight(content, source_mode="manual"):
    try:
        if "db_full" not in st.session_state: return False
        
        db = st.session_state.db_full
        
        data = {
            "content": content,
            "source": source_mode,
            "created_at": datetime.utcnow().isoformat(),
            # Si tienes filtro por proyecto, agrégalo aquí. Ej: "project_id": st.session_state.get("current_project_id")
        }
        
        db.table("project_memory").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error saving pin: {e}")
        return False

# --- NUEVA FUNCIÓN PARA LEER (AGREGA ESTO) ---
def get_project_memory():
    """Recupera los pines guardados para mostrarlos en el sidebar."""
    try:
        if "db_full" not in st.session_state: return []
        
        db = st.session_state.db_full
        
        # Traemos los últimos 20 pines ordenados por fecha
        response = db.table("project_memory").select("*").order("created_at", desc=True).limit(20).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching memory: {e}")
        return []
