import streamlit as st
import docx
import io
import os  
import uuid
from datetime import datetime
import re 
import time # Importante para la pausa de seguridad
from services.gemini_api import call_gemini_api, call_gemini_stream 
from services.supabase_db import log_query_event, supabase, get_daily_usage
from prompts import get_transcript_prompt, get_text_analysis_summary_prompt
import constants as c
from config import banner_file
from utils import reset_transcript_chat_workflow, render_process_status, process_text_with_tooltips

# --- GENERADORES ---
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx

# =====================================================
# MODO: ANÁLISIS DE TEXTOS (AUTO-REPARACIÓN + TOOLTIPS)
# =====================================================

TEXT_PROJECT_BUCKET = "text_project_files"

# --- Funciones de Carga ---

@st.cache_data(ttl=600, show_spinner=False)
def load_text_project_data(storage_folder_path: str):
    if not storage_folder_path:
        st.error("Error: Ruta vacía."); return []
    documents_list = [] 
    try:
        files_list = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(storage_folder_path)
        if not files_list: st.warning("Proyecto vacío."); return []
        docx_files = [f for f in files_list if f['name'].endswith('.docx')]
        
        st.write(f"Cargando {len(docx_files)} archivo(s)...")
        for file_info in docx_files:
            full_file_path = f"{storage_folder_path}/{file_info['name']}"
            try:
                res = supabase.storage.from_(TEXT_PROJECT_BUCKET).download(full_file_path)
                doc = docx.Document(io.BytesIO(res))
                text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                if text: documents_list.append({'source': file_info['name'], 'content': text})
            except Exception as e: st.error(f"Error en '{file_info['name']}': {e}"); continue 
        return documents_list
    except Exception as e: st.error(f"Error carga: {e}"); return []

# --- Funciones de UI ---

def show_text_project_creator(user_id, plan_limit):
    st.subheader("Crear Nuevo Proyecto de Texto")
    try:
        response = supabase.table("text_projects").select("id", count='exact').eq("user_id", user_id).execute()
        if response.count >= plan_limit and plan_limit != float('inf'):
            st.warning(f"Límite alcanzado ({int(plan_limit)})."); return
    except: pass

    with st.form("new_text_project_form"):
        p_name = st.text_input("Nombre del Proyecto*")
        p_brand = st.text_input("Marca*")
        p_year = st.number_input("Año*", min_value=2020, value=datetime.now().year)
        u_files = st.file_uploader("Archivos .docx*", type=["docx"], accept_multiple_files=True)
        if st.form_submit_button("Crear Proyecto"):
            if not all([p_name, p_brand, u_files]): st.warning("Completa campos."); return
            
            p_folder = f"{user_id}/{uuid.uuid4()}"
            
            with render_process_status("Subiendo archivos al repositorio...", expanded=True) as status:
                try:
                    for idx, f in enumerate(u_files):
                        status.write(f"Procesando {idx+1}/{len(u_files)}: {f.name}")
                        safe_name = re.sub(r'[^\w._-]', '', f.name.replace(' ', '_'))
                        supabase.storage.from_(TEXT_PROJECT_BUCKET).upload(f"{p_folder}/{safe_name}", f.getvalue(), {"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"})
                    
                    supabase.table("text_projects").insert({"project_name": p_name, "project_brand": p_brand, "project_year": int(p_year), "storage_path": p_folder, "user_id": user_id}).execute()
                    status.update(label="¡Proyecto creado!", state="complete", expanded=False)
                    st.success("Proyecto creado!"); st.rerun()
                except Exception as e: 
                    status.update(label="Error en creación", state="error")
                    st.error(f"Error: {e}")

def show_text_project_list(user_id):
    st.subheader("Mis Proyectos de Texto")
    try:
        projs = supabase.table("text_projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute().data
        if not projs: st.info("No hay proyectos."); return
        for p in projs:
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.markdown(f"**{p['project_name']}**"); c1.caption(f"{p.get('project_brand')} | {p.get('project_year')}")
                if c2.button("Analizar", key=f"an_{p['id']}", width='stretch', type="primary"):
                    st.session_state.mode_state.update({"ta_selected_project_id": p['id'], "ta_selected_project_name": p['project_name'], "ta_storage_path": p['storage_path']})
                    st.rerun()
                if c3.button("Eliminar", key=f"del_{p['id']}", width='stretch'):
                    try:
                        files = supabase.storage.from_(TEXT_PROJECT_BUCKET).list(p['storage_path'])
                        if files: supabase.storage.from_(TEXT_PROJECT_BUCKET).remove([f"{p['storage_path']}/{f['name']}" for f in files])
                        supabase.table("text_projects").delete().eq("id", p['id']).execute()
                        st.success("Eliminado."); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")
    except Exception as e: st.error(f"Error: {e}")

# --- Función de Análisis ---

def show_text_project_analyzer(summary_context, project_name, documents_list):
    st.markdown(f"### Análisis de Transcripciones: **{project_name}**")
    if st.button("← Volver"): st.session_state.mode_state = {}; st.rerun()
    st.divider()
    
    # Contexto limitado para rendimiento (200k caracteres)
    all_docs_text = "\n".join([f"--- DOC: {d['source']} ---\n{d['content']}" for d in documents_list])
    if len(all_docs_text) > 200000: 
        all_docs_text = all_docs_text[:200000] + "\n...(texto truncado por seguridad)"
    
    if "transcript_chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["transcript_chat_history"] = []

    # Mostrar historial (APLICANDO TOOLTIPS)
    for msg in st.session_state.mode_state["transcript_chat_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
            if msg['role'] == "assistant":
                # AQUÍ ESTÁ EL CAMBIO CLAVE: Usamos process_text_with_tooltips
                formatted_html = process_text_with_tooltips(msg["content"])
                st.markdown(formatted_html, unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])

    user_prompt = st.chat_input("Ej: ¿Cuáles son los hallazgos principales?")

    if user_prompt:
        st.session_state.mode_state["transcript_chat_history"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user", avatar="👤"): st.markdown(user_prompt)

        limit = st.session_state.plan_features.get('text_analysis_questions_per_day', 5)
        curr = get_daily_usage(st.session_state.user, c.MODE_TEXT_ANALYSIS) 

        if curr >= limit and limit != float('inf'):
            st.error(f"Límite diario alcanzado.")
        else:
            with st.chat_message("assistant", avatar="✨"):
                
                # --- SISTEMA DE AUTO-REPARACIÓN DE RESPUESTAS ---
                full_response = ""
                response_placeholder = st.empty()
                
                with render_process_status("🕵️ Analizando evidencia...", expanded=True) as status:
                    
                    # 1. Prompt Inicial
                    conciseness_instruction = (
                        "\n\n[INSTRUCCIÓN: Redacta un análisis fluido. "
                        "Usa el formato de citas rico: [Fuente: Archivo; Contexto: 'Cita textual...']. "
                        "NO uses tooltips complejos HTML, solo el formato texto plano.]"
                    )
                    
                    final_context = f"{all_docs_text}\n\n--- CONTEXTO GENERAL ---\n{summary_context}{conciseness_instruction}"
                    chat_prompt = get_transcript_prompt(final_context, user_prompt)
                    
                    # 2. Primera llamada (Streaming)
                    stream = call_gemini_stream(chat_prompt, generation_config_override={"max_output_tokens": 8192})
                    
                    if stream:
                        for chunk in stream:
                            full_response += chunk
                            response_placeholder.markdown(full_response + "▌") # Cursor visual
                        
                        # 3. Verificación de Corte
                        clean_text = full_response.strip()
                        if clean_text and not clean_text.endswith(('.', '!', '?', '"', '}', ']')):
                            
                            status.update(label="⚠️ Detectado corte de red. Auto-completando...", state="running")
                            
                            # 4. Segunda llamada (Continuación Silenciosa)
                            continuation_prompt = (
                                f"Tu respuesta anterior se cortó. Esto es lo último que escribiste:\n"
                                f"...{clean_text[-500:]}\n\n"
                                "POR FAVOR TERMINA LA FRASE Y LA IDEA COHERENTEMENTE. NO REPITAS LO ANTERIOR."
                            )
                            
                            stream_fix = call_gemini_stream(continuation_prompt, generation_config_override={"max_output_tokens": 4096})
                            
                            if stream_fix:
                                for chunk_fix in stream_fix:
                                    full_response += chunk_fix
                                    response_placeholder.markdown(full_response + "▌")
                        
                        status.update(label="¡Respuesta completa!", state="complete", expanded=False)
                        
                        # RENDERIZADO FINAL CON TOOLTIPS
                        # Convertimos el texto plano con formato [Fuente...] a HTML bonito
                        final_html = process_text_with_tooltips(full_response)
                        response_placeholder.markdown(final_html, unsafe_allow_html=True) 
                        
                        # Guardar en historial (Guardamos el texto original para re-procesarlo luego)
                        log_query_event(user_prompt, mode=f"{c.MODE_TEXT_ANALYSIS} (Chat)")
                        st.session_state.mode_state["transcript_chat_history"].append({"role": "assistant", "content": full_response})
                        
                    else:
                        status.update(label="Error en respuesta", state="error")
                        st.error("Error al obtener respuesta.")

    # Botones de exportación
    if st.session_state.mode_state["transcript_chat_history"]:
        st.divider() 
        c1, c2, c3 = st.columns(3)
        
        raw_text = f"# Análisis: {project_name}\n\n"
        raw_text += "\n\n".join(f"**{m['role'].upper()}:** {m['content']}" for m in st.session_state.mode_state["transcript_chat_history"])
        
        pdf = generate_pdf_html(raw_text, title=f"Reporte - {project_name}", banner_path=banner_file)
        if pdf: c1.download_button("PDF", data=pdf, file_name="analisis.pdf", mime="application/pdf", width='stretch')
        
        docx = generate_docx(raw_text, title=f"Reporte - {project_name}")
        if docx: c2.download_button("Word", data=docx, file_name="analisis.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width='stretch', type="primary")
        
        c3.button("Reiniciar", on_click=reset_transcript_chat_workflow, key="rst_chat", width='stretch')


def text_analysis_mode():
    st.subheader(c.MODE_TEXT_ANALYSIS); st.divider()
    uid = st.session_state.user_id
    limit = st.session_state.plan_features.get('transcript_file_limit', 0)

    # 1. Cargar Docs
    if "ta_selected_project_id" in st.session_state.mode_state and "ta_documents_list" not in st.session_state.mode_state:
        with render_process_status("Cargando archivos...", expanded=True) as status:
            docs = load_text_project_data(st.session_state.mode_state["ta_storage_path"]) 
            status.update(label="Carga completa", state="complete", expanded=False)
            
        if docs: st.session_state.mode_state["ta_documents_list"] = docs
        else: st.session_state.mode_state.pop("ta_selected_project_id")

    # 2. Resumen Inicial (Solo si no existe)
    if "ta_documents_list" in st.session_state.mode_state and "ta_summary_context" not in st.session_state.mode_state:
        with render_process_status("Generando visión general...", expanded=True) as status:
            docs = st.session_state.mode_state["ta_documents_list"]
            summ_in = "".join([f"\nDoc: {d['source']}\n{d['content'][:2500]}\n..." for d in docs])
            summ = call_gemini_api(get_text_analysis_summary_prompt(summ_in), generation_config_override={"max_output_tokens": 8192})
            status.update(label="Listo", state="complete", expanded=False)
            
        if summ: st.session_state.mode_state["ta_summary_context"] = summ; st.rerun()

    # 3. Vistas
    if "ta_summary_context" in st.session_state.mode_state:
        show_text_project_analyzer(
            st.session_state.mode_state["ta_summary_context"],
            st.session_state.mode_state["ta_selected_project_name"],
            st.session_state.mode_state["ta_documents_list"]
        )
    elif "ta_selected_project_id" in st.session_state.mode_state:
        st.info("Cargando...")
    else:
        with st.expander("Crear Proyecto", expanded=True): show_text_project_creator(uid, limit)
        st.divider(); show_text_project_list(uid)
