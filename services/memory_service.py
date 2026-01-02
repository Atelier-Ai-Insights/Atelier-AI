from services.supabase_db import supabase
import streamlit as st

def get_active_context():
    """
    Intenta determinar el contexto actual (Proyecto) basado en los filtros de la sidebar.
    Retorna un string, ej: "Proyecto Alpha, Proyecto Beta"
    """
    projects = st.session_state.get("filter_projects", [])
    if projects:
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
            "project_context": context,
            "insight_content": content
        }
        supabase.table("project_insights").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error saving insight: {e}")
        return False

def get_project_memory(context=None):
    """Recupera los insights guardados para el contexto actual."""
    try:
        user_id = st.session_state.user_id
        query = supabase.table("project_insights").select("*").eq("user_id", user_id)
        
        # Si hay un contexto específico (proyectos seleccionados), filtramos
        # Nota: Hacemos un filtro 'ilike' simple para traer memorias que contengan el nombre del proyecto
        active_projects = st.session_state.get("filter_projects", [])
        if active_projects:
            # Construimos una query OR para traer insights de cualquiera de los proyectos seleccionados
            # Supabase postgrest filter syntax para OR es un poco compleja, 
            # simplificaremos trayendo todo del usuario y filtrando en Python para este MVP
            pass 
            
        response = query.order("created_at", desc=True).execute()
        data = response.data
        
        # Filtro en memoria (Python) para mayor flexibilidad inicial
        if active_projects:
            filtered = []
            for item in data:
                # Si el insight pertenece a uno de los proyectos activos
                if any(proj in item['project_context'] for proj in active_projects):
                    filtered.append(item)
            return filtered
            
        return data
    except Exception as e:
        print(f"Error fetching memory: {e}")
        return []

def delete_insight(insight_id):
    try:
        supabase.table("project_insights").delete().eq("id", insight_id).execute()
        return True
    except: return False
