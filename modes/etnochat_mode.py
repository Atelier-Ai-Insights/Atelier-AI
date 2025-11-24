import streamlit as st
import docx
import io
import os  
import uuid
from datetime import datetime
import re 
from PIL import Image
import fitz 

from services.gemini_api import call_gemini_api, call_gemini_stream 
from services.supabase_db import log_query_event, supabase, get_daily_usage
from prompts import get_etnochat_prompt, get_media_transcription_prompt 
import constants as c
from reporting.pdf_generator import generate_pdf_html
# --- NUEVA IMPORTACIÓN ---
from reporting.docx_generator import generate_docx
from config import banner_file
from utils import reset_etnochat_chat_workflow

# ... (MANTENER LAS FUNCIONES DE CARGA 'load_etnochat_project_data', 'show_etnochat_project_creator' y 'show_etnochat_project_list' EXACTAMENTE IGUAL QUE ANTES) ...
# ... (SOLO VOY A MOSTRARTE LA FUNCIÓN DE ANÁLISIS 'show_etnochat_project_analyzer' Y 'etnochat_mode' QUE ES DONDE ESTÁN LOS BOTONES) ...

# COPIA Y PEGA DESDE AQUÍ HACIA ABAJO EN TU ARCHIVO PARA REEMPLAZAR LA PARTE FINAL:

def show_etnochat_project_analyzer(text_context, file_parts, project_name):
    st.markdown(f"### Analizando: **{project_name}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.mode_state = {}
        st.rerun()
        
    st.divider()
    st.header("Chat Etnográfico Multimodal")
    
    if "etno_chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["etno_chat_history"] = []

    for msg in st.session_state.mode_state["etno_chat_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
            st.markdown(msg["content"])

    user_prompt = st.chat_input("Haz una pregunta sobre los archivos...")

    if user_prompt:
        st.session_state.mode_state["etno_chat_history"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"): st.markdown(user_prompt)

        question_limit = st.session_state.plan_features.get('etnochat_questions_per_day', 5)
        current_queries = get_daily_usage(st.session_state.user, c.MODE_ETNOCHAT) 

        if current_queries >= question_limit and question_limit != float('inf'):
            st.error(f"Límite de preguntas diarias alcanzado.")
            st.session_state.mode_state["etno_chat_history"].pop()
            return

        with st.chat_message("assistant", avatar="✨"):
            history_str = "\n".join(f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["etno_chat_history"][-10:])
            prompt_text = get_etnochat_prompt(history_str, text_context)
            final_prompt_list = [prompt_text] + file_parts
            
            stream = call_gemini_stream(final_prompt_list) 

            if stream:
                response_text = st.write_stream(stream) 
                log_query_event(user_prompt, mode=c.MODE_ETNOCHAT)
                st.session_state.mode_state["etno_chat_history"].append({"role": "assistant", "content": response_text})
            else:
                st.error("Error al obtener respuesta multimodal.")
                st.session_state.mode_state["etno_chat_history"].pop()

    # --- BOTONES DE DESCARGA Y REINICIO ---
    if st.session_state.mode_state["etno_chat_history"]:
        st.divider() 
        
        # Preparar contenido para exportar
        chat_content_raw = f"# Reporte Etnográfico: {project_name}\n\n"
        chat_content_raw += "\n\n".join(f"**{m['role'].upper()}:** {m['content']}" for m in st.session_state.mode_state["etno_chat_history"])
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            pdf_bytes = generate_pdf_html(chat_content_raw.replace("](#)", "]"), title=f"EtnoChat - {project_name}", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button("📄 Chat en PDF", data=pdf_bytes, file_name="etno_chat.pdf", mime="application/pdf", width='stretch')
        
        with col2:
            docx_bytes = generate_docx(chat_content_raw, title=f"EtnoChat - {project_name}")
            if docx_bytes:
                st.download_button("📝 Chat en Word", data=docx_bytes, file_name="etno_chat.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width='stretch', type="primary")

        with col3: 
            st.button("🔄 Reiniciar Chat", on_click=reset_etnochat_chat_workflow, key="new_etno_chat_btn", width='stretch')

# --- FUNCIÓN PRINCIPAL DEL MODO ---
# (ESTA PARTE LA DEBES MANTENER IGUAL, SOLO ASEGÚRATE DE QUE ESTÉ AL FINAL)

def etnochat_mode():
    st.subheader(c.MODE_ETNOCHAT)
    # ... (Igual que antes: Carga de proyecto, transcribir, etc) ...
    # ... Solo cambiamos la llamada a show_etnochat_project_analyzer que acabamos de definir arriba ...
    
    # 1. Cargar datos... (Igual)
    if "etno_selected_project_id" in st.session_state.mode_state and "etno_file_parts" not in st.session_state.mode_state:
        # (Lógica de carga que ya tenías, asegúrate de importar load_etnochat_project_data si no está en este bloque)
        from modes.etnochat_mode import load_etnochat_project_data # Auto-referencia temporal o asegurar que la función está arriba
        
        text_ctx, file_parts = load_etnochat_project_data(st.session_state.mode_state["etno_storage_path"]) 
        if text_ctx is not None:
            st.session_state.mode_state["etno_context_str"] = text_ctx
            st.session_state.mode_state["etno_file_parts"] = file_parts

    # Lógica de Vistas
    if "etno_file_parts" in st.session_state.mode_state:
        show_etnochat_project_analyzer( 
            st.session_state.mode_state["etno_context_str"],
            st.session_state.mode_state["etno_file_parts"],
            st.session_state.mode_state["etno_selected_project_name"]
        )
    elif "etno_selected_project_id" in st.session_state.mode_state:
        st.info("Iniciando carga...")
    else:
        # Mostrar lista y creador... (Igual que antes)
        user_id = st.session_state.user_id
        plan = st.session_state.plan_features
        
        # Importar funciones UI si no están definidas en este archivo (o copiarlas si las tienes arriba)
        # show_etnochat_project_creator(...)
        # show_etnochat_project_list(...)
        pass # (Aquí va el resto de tu código original de gestión)
