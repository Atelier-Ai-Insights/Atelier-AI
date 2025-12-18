import streamlit as st
import docx
import io
import os  
import uuid
from datetime import datetime
import re 
from services.gemini_api import call_gemini_api, call_gemini_stream 
from services.supabase_db import log_query_event, supabase, get_daily_usage
from prompts import get_transcript_prompt, get_autocode_prompt, get_text_analysis_summary_prompt
import constants as c
from reporting.pdf_generator import generate_pdf_html
# --- NUEVA IMPORTACIÓN ---
from reporting.docx_generator import generate_docx
from config import banner_file
from utils import reset_transcript_chat_workflow, build_rag_context

# =====================================================
# MODO: ANÁLISIS DE TEXTOS (OPTIMIZADO CON RAG + DOCX)
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
            with st.spinner("Subiendo archivos..."):
                try:
                    for f in u_files:
                        safe_name = re.sub(r'[^\w._-]', '', f.name.replace(' ', '_'))
                        supabase.storage.from_(TEXT_PROJECT_BUCKET).upload(f"{p_folder}/{safe_name}", f.getvalue(), {"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"})
                    supabase.table("text_projects").insert({"project_name": p_name, "project_brand": p_brand, "project_year": int(p_year), "storage_path": p_folder, "user_id": user_id}).execute()
                    st.success("Proyecto creado!"); st.rerun()
                except Exception as e: st.error(f"Error: {e}")

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

# --- Función de Análisis (ACTUALIZADA) ---

def show_text_project_analyzer(summary_context, project_name, documents_list):
    st.markdown(f"### Analizando: **{project_name}**")
    if st.button("← Volver"): st.session_state.mode_state = {}; st.rerun()
    st.divider()
    
    tab_chat, tab_autocode = st.tabs(["Análisis de Notas y Transcripciones", "Auto-Codificación"])

    with tab_chat:
        st.header("Análisis de Notas y Transcripciones")
        if "transcript_chat_history" not in st.session_state.mode_state: 
            st.session_state.mode_state["transcript_chat_history"] = []

        for msg in st.session_state.mode_state["transcript_chat_history"]:
            with st.chat_message(msg["role"], avatar="✨" if msg['role'] == "assistant" else "👤"):
                st.markdown(msg["content"])

        user_prompt = st.chat_input("Ej: ¿Qué opinan los usuarios sobre el precio?")

        if user_prompt:
            st.session_state.mode_state["transcript_chat_history"].append({"role": "user", "content": user_prompt})
            with st.chat_message("user", avatar="👤"): st.markdown(user_prompt)

            limit = st.session_state.plan_features.get('text_analysis_questions_per_day', 5)
            curr = get_daily_usage(st.session_state.user, c.MODE_TEXT_ANALYSIS) 

            if curr >= limit and limit != float('inf'):
                st.error(f"Límite diario alcanzado.")
            else:
                with st.chat_message("assistant", avatar="✨"):
                    status_ph = st.empty()
                    status_ph.markdown("🕵️ **Explorando documentos...**")
                    rag_chunks = build_rag_context(user_prompt, documents_list, max_chars=30000)
                    
                    status_ph.markdown("✨ **Generando respuesta...**")
                    final_context = f"--- RESUMEN ---\n{summary_context}\n--- EVIDENCIA ---\n{rag_chunks}"
                    chat_prompt = get_transcript_prompt(final_context, user_prompt)
                    
                    stream = call_gemini_stream(chat_prompt) 
                    status_ph.empty()

                    if stream:
                        response_text = st.write_stream(stream)
                        log_query_event(user_prompt, mode=f"{c.MODE_TEXT_ANALYSIS} (Chat)")
                        st.session_state.mode_state["transcript_chat_history"].append({"role": "assistant", "content": response_text})
                    else: st.error("Error al obtener respuesta.")

        if st.session_state.mode_state["transcript_chat_history"]:
            st.divider() 
            c1, c2, c3 = st.columns(3)
            
            # Construir texto para exportar
            raw_text = f"# Chat Transcripciones: {project_name}\n\n"
            raw_text += "\n\n".join(f"**{m['role'].upper()}:** {m['content']}" for m in st.session_state.mode_state["transcript_chat_history"])
            
            # PDF
            pdf = generate_pdf_html(raw_text.replace("](#)", "]"), title=f"Chat - {project_name}", banner_path=banner_file)
            if pdf: c1.download_button("📄 Descargar PDF", data=pdf, file_name="chat.pdf", mime="application/pdf", width='stretch')
            
            # WORD (Nuevo)
            docx = generate_docx(raw_text, title=f"Chat - {project_name}")
            if docx: c2.download_button("📝 Descargar Word", data=docx, file_name="chat.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width='stretch', type="primary")
            
            # Reiniciar
            c3.button("🔄 Reiniciar", on_click=reset_transcript_chat_workflow, key="rst_chat", width='stretch')

    with tab_autocode:
        st.header("Auto-Codificación")
        if "autocode_result" in st.session_state.mode_state:
            st.markdown(st.session_state.mode_state["autocode_result"])
            
            st.divider()
            c1, c2, c3 = st.columns(3)
            
            # PDF
            pdf = generate_pdf_html(st.session_state.mode_state["autocode_result"], title="Temas", banner_path=banner_file)
            if pdf: c1.download_button("📄 Descargar PDF", data=pdf, file_name="temas.pdf", width='stretch')
            
            # WORD (Nuevo)
            docx = generate_docx(st.session_state.mode_state["autocode_result"], title="Auto-Codificación")
            if docx: c2.download_button("📝 Descargar Word", data=docx, file_name="temas.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width='stretch', type="primary")
            
            # Reiniciar
            if c3.button("🔄 Nuevo análisis", width='stretch'): 
                st.session_state.mode_state.pop("autocode_result", None); st.rerun()
        else:
            topic = st.text_input("Tema principal:", placeholder="Ej: Percepción de marca")
            if st.button("Analizar", type="primary", width='stretch'):
                if not topic.strip(): st.warning("Describe el tema.")
                else:
                    status_ph = st.empty()
                    status_ph.markdown("🔍 **Analizando patrones...**")
                    prompt = get_autocode_prompt(summary_context, topic)
                    stream = call_gemini_stream(prompt)
                    status_ph.empty()
                    
                    if stream:
                        res = st.write_stream(stream)
                        st.session_state.mode_state["autocode_result"] = res
                        log_query_event(f"Autocode: {topic}", mode=f"{c.MODE_TEXT_ANALYSIS} (Autocode)")
                        st.rerun()

def text_analysis_mode():
    st.subheader(c.MODE_TEXT_ANALYSIS); st.divider()
    uid = st.session_state.user_id
    limit = st.session_state.plan_features.get('transcript_file_limit', 0)

    # 1. Cargar Docs
    if "ta_selected_project_id" in st.session_state.mode_state and "ta_documents_list" not in st.session_state.mode_state:
        ph = st.empty(); ph.info("📥 Descargando archivos...")
        docs = load_text_project_data(st.session_state.mode_state["ta_storage_path"]) 
        ph.empty()
        if docs: st.session_state.mode_state["ta_documents_list"] = docs
        else: st.session_state.mode_state.pop("ta_selected_project_id")

    # 2. Generar Resumen
    if "ta_documents_list" in st.session_state.mode_state and "ta_summary_context" not in st.session_state.mode_state:
        ph = st.empty(); ph.info("🧠 Generando resumen inicial...")
        docs = st.session_state.mode_state["ta_documents_list"]
        summ_in = "".join([f"\nDoc: {d['source']}\n{d['content'][:2500]}\n..." for d in docs])
        summ = call_gemini_api(get_text_analysis_summary_prompt(summ_in), generation_config_override={"max_output_tokens": 8192})
        ph.empty()
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
        with st.expander("➕ Crear Proyecto", expanded=True): show_text_project_creator(uid, limit)
        st.divider(); show_text_project_list(uid)
