import streamlit as st
import json
from utils import get_relevant_info, reset_chat_workflow, clean_gemini_json
from services.gemini_api import call_gemini_api
from services.supabase_db import get_daily_usage, log_query_event, supabase 
from services.memory_service import save_project_insight, get_project_memory, delete_insight 
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_grounded_chat_prompt, get_followup_suggestions_prompt
import constants as c 

# =====================================================
# FUNCIONES AUXILIARES
# =====================================================
def update_query_rating(query_id, rating):
    try:
        supabase.table("queries").update({"rating": rating}).eq("id", query_id).execute()
    except Exception as e: print(f"Error rating: {e}")

# =====================================================
# MODO: CHAT DE CONSULTA DIRECTA (FINAL)
# =====================================================

def grounded_chat_mode(db, selected_files, sidebar_container=None):
    
    # --- BARRA LATERAL: BITÁCORA DE PROYECTO ---
    target_area = sidebar_container if sidebar_container else st.sidebar
    
    with target_area:
        st.markdown("### 🧠 Bitácora del Proyecto")
        memories = get_project_memory()
        
        if memories:
            for mem in memories:
                # CAMBIO: El título es el 'project_context' (Nombre del Proyecto/Filtro)
                pin_title = mem.get('project_context', 'Sin Título')
                
                with st.expander(f"📌 {pin_title}", expanded=False):
                    # El contenido es el insight
                    st.caption(f"📅 {mem['created_at'][:10]}")
                    
                    c_view, c_del = st.columns([1, 1])
                    with c_view:
                        if st.button("👁️ Leer", key=f"view_mem_{mem['id']}", use_container_width=True):
                            st.session_state.focused_insight = mem
                            st.rerun()
                    with c_del:
                        if st.button("🗑️", key=f"del_mem_{mem['id']}", use_container_width=True, help="Eliminar"):
                            delete_insight(mem['id'])
                            if st.session_state.get("focused_insight", {}).get("id") == mem['id']:
                                del st.session_state.focused_insight
                            st.rerun()
        else:
            st.caption("No hay insights guardados.")
            
        st.divider() 
    
    # --- ÁREA PRINCIPAL ---
    st.subheader("Chat de Consulta Directa")
    
    # VISOR DE INSIGHT
    if "focused_insight" in st.session_state:
        insight = st.session_state.focused_insight
        with st.container(border=True):
            col_h1, col_h2 = st.columns([8, 1])
            with col_h1: st.markdown(f"**📌 Insight Guardado:** *{insight['project_context']}*")
            with col_h2:
                if st.button("✕", key="close_insight_view"):
                    del st.session_state.focused_insight
                    st.rerun()
            st.info(insight['insight_content'], icon="🧠")

    # 1. VALIDACIÓN
    if not selected_files:
        st.info("👈 **Para comenzar:** Selecciona una Marca, Año y Proyecto en el menú lateral.")
        if "chat_history" not in st.session_state.mode_state:
            st.session_state.mode_state["chat_history"] = []
    else:
        st.caption(f"Analizando **{len(selected_files)} documento(s)** seleccionados.")

    # 2. INICIALIZACIÓN
    if "chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["chat_history"] = []

    # 3. MOSTRAR HISTORIAL
    for idx, msg in enumerate(st.session_state.mode_state["chat_history"]):
        with st.chat_message(msg['role'], avatar="✨" if msg['role'] == "Asistente" else "👤"): 
            st.markdown(msg['message'])
            if msg['role'] == "Asistente":
                c_feed, c_spacer, c_pin = st.columns([2, 6, 1])
                with c_feed:
                    if 'query_id' in msg:
                        rating = st.feedback("thumbs", key=f"feed_{msg.get('query_id', idx)}")
                        if rating is not None: update_query_rating(msg['query_id'], 1 if rating == 1 else -1)
                with c_pin:
                    with st.popover("📌", use_container_width=False, help="Guardar hallazgo"):
                        st.markdown("**¿Guardar en Bitácora?**")
                        if st.button("Confirmar", key=f"save_mem_{idx}"):
                            if save_project_insight(msg['message']):
                                st.toast("✅ Guardado en Bitácora"); st.rerun() 

    # 4. GESTIÓN DE INPUT
    prompt_to_process = None
    
    # A. Botones de Sugerencia
    if selected_files and "chat_suggestions" in st.session_state.mode_state:
        suggestions = st.session_state.mode_state.get("chat_suggestions", [])
        if suggestions:
            st.write("") 
            st.caption("🤔 **Temas sugeridos:**")
            for i, sugg in enumerate(suggestions):
                if st.button(f"👉 {sugg}", key=f"sugg_btn_{i}", use_container_width=True):
                    prompt_to_process = sugg
            st.write("") 

    # B. Input Usuario
    user_input = st.chat_input("Escribe tu pregunta...", disabled=not selected_files)
    if user_input:
        prompt_to_process = user_input

    # 5. PROCESAMIENTO
    if prompt_to_process and selected_files:
        # Limpiamos sugerencias viejas
        if "chat_suggestions" in st.session_state.mode_state:
            del st.session_state.mode_state["chat_suggestions"]
            
        st.session_state.mode_state["chat_history"].append({"role": "Usuario", "message": prompt_to_process})
        with st.chat_message("Usuario", avatar="👤"): st.markdown(prompt_to_process)
            
        # Límite consultas
        query_limit = st.session_state.plan_features.get('chat_queries_per_day', 0)
        current_queries = get_daily_usage(st.session_state.user, c.MODE_CHAT)
        if current_queries >= query_limit and query_limit != float('inf'): 
            st.error(f"Límite alcanzado."); return
            
        with st.chat_message("Asistente", avatar="✨"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Pensando...")
            
            # RAG + Memoria
            relevant_info = get_relevant_info(db, prompt_to_process, selected_files)
            memory_list = get_project_memory() # Trae todas las memorias
            memory_text = "\n".join([f"- {m['insight_content']}" for m in memory_list])
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.mode_state["chat_history"][-10:])
            
            grounded_prompt = get_grounded_chat_prompt(conversation_history, relevant_info, long_term_memory=memory_text)
            
            response = call_gemini_api(grounded_prompt)
            
            if response: 
                message_placeholder.markdown(response)
                
                # --- LÓGICA DE SUGERENCIAS ---
                # CAMBIO CLAVE: Definir qué sugerir basado en el turno de la conversación
                
                # Turno 1 (Acaba de responder la 1ra pregunta, len history es 2: User + Assistant)
                if len(st.session_state.mode_state["chat_history"]) < 2: 
                    # Forzamos las 3 estáticas
                    st.session_state.mode_state["chat_suggestions"] = [
                        "Enumera los objetivos de investigación",
                        "Detalles de la metodología y ficha técnica",
                        "Principales hallazgos"
                    ]
                else:
                    # Turno 2 en adelante: Usamos IA Follow-up (o nada, si se prefiere)
                    try:
                        prompt_followup = get_followup_suggestions_prompt(response)
                        resp_sugg = call_gemini_api(prompt_followup, generation_config_override={"response_mime_type": "application/json"})
                        if resp_sugg:
                            new_suggestions = json.loads(clean_gemini_json(resp_sugg))
                            st.session_state.mode_state["chat_suggestions"] = new_suggestions
                    except: st.session_state.mode_state["chat_suggestions"] = []

                # Logging
                try:
                    res_log = log_query_event(prompt_to_process, mode=c.MODE_CHAT)
                    query_id = res_log if res_log else f"temp_{len(st.session_state.mode_state['chat_history'])}"
                except: query_id = None

                st.session_state.mode_state["chat_history"].append({
                    "role": "Asistente", "message": response, "query_id": query_id
                })
                st.rerun()
            else: 
                message_placeholder.error("Error al generar respuesta.")
                
    # 6. EXPORTACIÓN
    if st.session_state.mode_state["chat_history"]:
        st.divider()
        col1, col2 = st.columns([1,1])
        with col1:
            chat_content_raw = "\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.mode_state["chat_history"])
            pdf_bytes = generate_pdf_html(chat_content_raw.replace("](#)", "]"), title="Historial Consulta", banner_path=banner_file)
            if pdf_bytes: st.download_button("📥 PDF", data=pdf_bytes, file_name="chat.pdf", mime="application/pdf", use_container_width=True)
        with col2: 
            def clean_all():
                reset_chat_workflow()
                if "chat_suggestions" in st.session_state.mode_state: del st.session_state.mode_state["chat_suggestions"]
            st.button("🗑️ Limpiar", on_click=clean_all, key="new_grounded_chat_btn", use_container_width=True)
