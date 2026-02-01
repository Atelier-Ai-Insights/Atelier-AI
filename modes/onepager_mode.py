import streamlit as st
import time
import json
from datetime import datetime

# --- IMPORTACIONES ESENCIALES ---
from services.gemini_api import call_gemini_api
from utils import get_relevant_info
from prompts import get_onepager_prompt
# Asegúrate de haber creado el archivo reporting/pptx_generator.py en el paso anterior
from reporting.pptx_generator import create_pptx_from_structure
from services.supabase_db import get_monthly_usage, log_query_event
import constants as c

def one_pager_ppt_mode(db, selected_files):
    st.subheader("Generador de One Pagers (PPTX)")
    st.caption("Crea diapositivas estratégicas resumidas listas para descargar.")
    
    # 1. Validación de Cuota
    limit = st.session_state.plan_features.get('one_pagers_per_month', 5)
    usage = get_monthly_usage(st.session_state.user, c.MODE_ONE_PAGER)
    
    if limit != float('inf'):
        progress = min(usage / limit, 1.0)
        st.progress(progress, text=f"Uso mensual: {usage}/{int(limit)}")
        if usage >= limit:
            st.error("Has alcanzado tu límite mensual.")
            return

    # 2. Input del Usuario
    user_topic = st.text_input("Tema del One Pager:", placeholder="Ej: Resumen de tendencias en snacks saludables...")
    
    if not selected_files:
        st.info("👈 Selecciona documentos para comenzar.")
        return

    # 3. Botón de Acción (Sin feedback, directo al grano)
    if st.button("Generar PPTX", type="primary", width="stretch"):
        if not user_topic:
            st.warning("Escribe un tema."); return

        # --- PROCESO ---
        status_box = st.empty()
        
        with status_box.status("Trabajando en tu diapositiva...", expanded=True) as status:
            
            # A. Contexto
            status.write("🔍 Leyendo documentos...")
            context = get_relevant_info(db, user_topic, selected_files)
            
            if not context:
                status.update(label="Falta información", state="error")
                return

            # B. Estructura con IA
            status.write("Diseñando estructura...")
            prompt = get_onepager_prompt(user_topic, context)
            response_json = call_gemini_api(prompt, generation_config_override={"response_mime_type": "application/json"})
            
            if response_json:
                try:
                    # C. Generación de Archivo
                    status.write("Dibujando PowerPoint...")
                    data = json.loads(response_json)
                    if isinstance(data, list): data = data[0]
                    
                    pptx_bytes = create_pptx_from_structure(data)
                    
                    # Guardar en sesión
                    st.session_state.mode_state["last_onepager_pptx"] = pptx_bytes
                    st.session_state.mode_state["last_onepager_name"] = f"OnePager_{user_topic[:20].replace(' ','_')}.pptx"
                    
                    # Log
                    try: log_query_event(f"OnePager: {user_topic}", mode=c.MODE_ONE_PAGER)
                    except: pass
                    
                    status.update(label="¡Listo!", state="complete", expanded=False)
                    time.sleep(0.5)
                    status_box.empty()

                except Exception as e:
                    status.update(label="Error técnico", state="error")
                    st.error(f"Detalle del error: {e}")
            else:
                status.update(label="Error de IA", state="error")

    # 4. Zona de Descarga (Limpia)
    if "last_onepager_pptx" in st.session_state.mode_state:
        st.success("✅ Tu presentación ha sido generada.")
        
        st.download_button(
            label="Descargar PowerPoint (.pptx)",
            data=st.session_state.mode_state["last_onepager_pptx"],
            file_name=st.session_state.mode_state.get("last_onepager_name", "presentacion.pptx"),
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            width="stretch",
            type="primary"
        )
