import streamlit as st
import uuid
import os
import datetime
from services.supabase_db import supabase

PROJECT_BUCKET = "project_files"

def show_project_creator(user_id, plan_limit):
    """Componente UI para crear nuevos proyectos de análisis de datos (Excel)."""
    st.subheader("Crear Nuevo Proyecto")
    
    # Validar límites
    try:
        response = supabase.table("projects").select("id", count='exact').eq("user_id", user_id).execute()
        if response.count >= plan_limit and plan_limit != float('inf'):
            st.warning(f"Límite de proyectos alcanzado ({int(plan_limit)}).")
            return
    except Exception as e: 
        st.error(f"Error verificando límites: {e}")
        return

    with st.form("new_project_form"):
        project_name = st.text_input("Nombre del Proyecto*", placeholder="Ej: Q1 Sales Tracking")
        project_brand = st.text_input("Marca*", placeholder="Ej: Brand X")
        project_year = st.number_input("Año*", min_value=2020, value=datetime.datetime.now().year)
        uploaded_file = st.file_uploader("Archivo Excel (.xlsx)*", type=["xlsx"])
        
        if st.form_submit_button("Crear Proyecto"):
            if not all([project_name, project_brand, uploaded_file]):
                st.warning("Completa los campos obligatorios.")
            else:
                with st.spinner("Subiendo archivo..."):
                    try:
                        file_ext = os.path.splitext(uploaded_file.name)[1]
                        path = f"{user_id}/{uuid.uuid4()}{file_ext}"
                        
                        supabase.storage.from_(PROJECT_BUCKET).upload(
                            path, 
                            uploaded_file.getvalue(), 
                            {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
                        )
                        
                        supabase.table("projects").insert({
                            "project_name": project_name, 
                            "project_brand": project_brand, 
                            "project_year": int(project_year), 
                            "storage_path": path, 
                            "user_id": user_id
                        }).execute()
                        
                        st.success("¡Proyecto creado!")
                        st.rerun()
                    except Exception as e: 
                        st.error(f"Error: {e}")

def show_project_list(user_id):
    """Componente UI para listar y eliminar proyectos."""
    st.subheader("Mis Proyectos")
    try:
        projs = supabase.table("projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute().data
        if not projs: 
            st.info("No hay proyectos creados.")
            return

        for p in projs:
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.markdown(f"**{p['project_name']}**"); c1.caption(f"{p.get('project_brand')} | {p.get('project_year')}")
                
                if c2.button("Analizar", key=f"an_{p['id']}", width='stretch', type="primary"):
                    st.session_state.mode_state.update({
                        "da_selected_project_id": p['id'], 
                        "da_selected_project_name": p['project_name'], 
                        "da_storage_path": p['storage_path'],
                        "da_current_sub_mode": "Tabla Dinámica"
                    })
                    st.rerun()
                    
                if c3.button("Eliminar", key=f"del_{p['id']}", width='stretch'):
                    try:
                        supabase.storage.from_(PROJECT_BUCKET).remove([p['storage_path']])
                        supabase.table("projects").delete().eq("id", p['id']).execute()
                        st.success("Eliminado.")
                        st.rerun()
                    except Exception as e: 
                        st.error(f"Error: {e}")
    except Exception as e: 
        st.error(f"Error listando proyectos: {e}")
