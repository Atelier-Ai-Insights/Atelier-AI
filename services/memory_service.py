from services.supabase_db import supabase
import streamlit as st

def get_active_context():
    """
    Determina el nombre del contexto para guardarlo como título del Pin.
    Prioridad: Proyectos > Marca+Año > General.
    """
    projects = st.session_state.get("filter_projects", [])
    if projects:
        # Si hay varios, los unimos, si es uno, queda el nombre del proyecto
        return ", ".join(projects)
    
    # Fallback: Si no hay filtro de proyecto, usar Marca + Año
    brands = st.session_state.get("filter_marcas", [])
    years = st.session_state.get("filter_years", [])
    
    if brands:
        return f"{', '.join(brands)} ({', '.join(years) if years else 'General'})"
    
    return "Contexto General"

def save_project_insight(content, context=None):
    """Guarda un hallazgo en la memoria de largo plazo."""
    try:
        user_id = st.session_state.user_id
        if not context:
            context = get_active_context()
            
        data = {
            "user_id": user_id,
            "project_context": context, # Aquí se guarda el Nombre del Proyecto
            "insight_content": content
        }
        supabase.table("project_insights").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error saving insight: {e}")
        return False

def get_project_memory(context=None):
    """
    Recupera los insights guardados.
    CAMBIO: Ahora retorna TODOS los insights del usuario, ignorando los filtros activos
    para cumplir el requerimiento de 'siempre visibles'.
    """
    try:
        user_id = st.session_state.user_id
        # Traemos todo lo del usuario ordenado por fecha
        query = supabase.table("project_insights").select("*").eq("user_id", user_id).order("created_at", desc=True)
        response = query.execute()
        return response.data
            
    except Exception as e:
        print(f"Error fetching memory: {e}")
        return []

def delete_insight(insight_id):
    try:
        supabase.table("project_insights").delete().eq("id", insight_id).execute()
        return True
    except: return False
