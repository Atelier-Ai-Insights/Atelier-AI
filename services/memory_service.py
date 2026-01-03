import streamlit as st
from datetime import datetime
from services.supabase_db import supabase # Importamos supabase directamente

# 1. GUARDAR (PIN)
def save_project_insight(content, source_mode="manual"):
    try:
        data = {
            "content": content,
            "source": source_mode,
            "created_at": datetime.utcnow().isoformat(),
            # Opcional: Si tienes user_id en session_state, descomenta esto:
            # "user_id": st.session_state.get("user_id")
        }
        
        # Insertamos en Supabase
        supabase.table("project_memory").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error saving pin: {e}")
        return False

# 2. LEER (PARA EL SIDEBAR)
def get_project_memory():
    """Recupera los pines guardados para mostrarlos en el sidebar."""
    try:
        # Traemos todo (*) incluyendo el 'id' para poder borrar
        response = supabase.table("project_memory").select("*").order("created_at", desc=True).limit(20).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching memory: {e}")
        return []

# 3. BORRAR (ESTA ES LA QUE FALTABA Y CAUSABA EL ERROR)
def delete_project_memory(pin_id):
    """Elimina un pin específico por su ID."""
    try:
        supabase.table("project_memory").delete().eq("id", pin_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting pin: {e}")
        return False
