import streamlit as st
import time
import json
from datetime import datetime

# --- IMPORTACIONES ACTUALIZADAS ---
from services.gemini_api import call_gemini_api, call_gemini_stream
from utils import get_relevant_info, process_text_with_tooltips
# Asegúrate de que prompts.py ya tenga la función get_onepager_prompt (paso anterior)
from prompts import get_onepager_prompt
from reporting.pptx_generator import create_pptx_from_structure
from services.supabase_db import get_monthly_usage, log_query_event, log_message_feedback
import constants as c

def one_pager_ppt_mode(db, selected_files):
    st.subheader("Generador de One Pagers (PPTX)")
    st.caption("Crea diapositivas estratégicas resumidas listas para descargar.")
    
    # Validación de Plan (Mensual)
    limit = st.session_state.plan_features.get('one_pagers_per_month', 5)
    usage = get_monthly_usage(st.session_state.user, c.MODE_ONE_PAGER)
    
    # Barra de progreso de cuota
    if limit != float('inf'):
        progress = min(usage / limit, 1.0)
        st.progress(progress, text=f"Uso mensual: {usage}/{int(limit)} One Pagers")
        if usage >= limit:
            st.error("Has alcanzado tu límite mensual de One Pagers.")
            return

    # Input Usuario
    user_topic = st.text_input("Tema del One Pager:", placeholder="Ej: Resumen de tendencias en snacks saludables...")
    
    if not selected_files:
        st.info("👈 Selecciona documentos para comenzar.")
        return

    # --- CAMBIO AQUI: width="stretch" en lugar de use_container_width=True ---
    if st.button("Generar PPTX", type="primary", width="stretch"):
        if not user_topic:
            st.warning("Escribe un tema."); return

        # --- INICIO PROCESO VISUAL ---
        status_box = st.empty()
        
        with status_box.status("Diseñando diapositiva estratégica...", expanded=True) as status:
            
            # Paso 1: Búsqueda
            status.write("Escaneando documentos relevantes...")
            context = get_relevant_info(db, user_topic, selected_files)
            
            if not context:
                status.update(label="Datos insuficientes", state="error")
                return

            # Paso 2: Generación de Estructura JSON
            status.write("Estructurando contenido visual (Título, Bullets, Insights)...")
            prompt = get_onepager_prompt(user_topic, context)
            
            # Usamos call_gemini_api directo porque necesitamos JSON estricto
            response_json_str = call_gemini_api(prompt, generation_config_override={"response_mime_type": "application/json"})
            
            if response_json_str:
                try:
                    # Paso 3: Parseo y Creación de Archivo
                    status.write("Renderizando archivo PowerPoint...")
                    data = json.loads(response_json_str)
                    
                    if isinstance(data, list): data = data[0]
                    
                    # Generar el PPTX binario
                    pptx_bytes = create_pptx_from_structure(data)
                    
                    # Guardar en estado
                    st.session_state.mode_state["last_onepager_pptx"] = pptx_bytes
                    st.session_state.mode_state["last_onepager_data"] = data
                    
                    # Log de éxito
                    log_query_event(f"OnePager: {user_topic}", mode=c.MODE_ONE_PAGER)
                    
                    status.update(label="¡One Pager Listo!", state="complete", expanded=False)
                    time.sleep(0.7)
                    status_box.empty() # Auto-limpieza

                except Exception as e:
                    status.update(label="Error de formato", state="error")
                    st.error(f"Error procesando la respuesta: {e}")
            else:
                status.update(label="Error de IA", state="error")

    # --- RESULTADO Y DESCARGA ---
    if "last_onepager_pptx" in st.session_state.mode_state:
        data = st.session_state.mode_state.get("last_onepager_data", {})
        
        with st.container(border=True):
            st.markdown(f"### {data.get('titulo', 'Sin Título')}")
            st.caption(data.get('subtitulo', ''))
            
            st.markdown("**Puntos Clave:**")
            for p in data.get('puntos_clave', []):
                st.markdown(f"- {p}")
            
            if data.get('insight_principal'):
                st.info(f"💡 **Insight:** {data.get('insight_principal')}")

        c_up, c_down, c_dl = st.columns([1, 1, 4])
        key_id = str(hash(data.get('titulo', 'op')))
        
        with c_up:
            if st.button("👍", key=f"op_up_{key_id}"):
                log_message_feedback(str(data), "one_pager", "up")
                st.toast("Feedback guardado")
        
        with c_down:
            if st.button("👎", key=f"op_down_{key_id}"):
                log_message_feedback(str(data), "one_pager", "down")
                st.toast("Gracias por el feedback")
                
        with c_dl:
            # --- CAMBIO AQUI: width="stretch" ---
            st.download_button(
                label="Descargar .PPTX",
                data=st.session_state.mode_state["last_onepager_pptx"],
                file_name=f"OnePager_{user_topic.replace(' ','_')}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                width="stretch",
                type="primary"
            )
