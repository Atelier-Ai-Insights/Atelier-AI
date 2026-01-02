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
# MODO: CHAT DE CONSULTA DIRECTA (ESTILO MINIMALISTA)
# =====================================================

def grounded_chat_mode(db, selected_files, sidebar_container=None):
    
    # --- BARRA LATERAL: BITÁCORA DE PROYECTO (ESTILO LISTA) ---
    target_area = sidebar_container if sidebar_container else st.sidebar
    
    with target_area:
        st.divider() 
        # Encabezado con estilo
        st.markdown("### 🧠 Bitácora")
        memories = get_project_memory()
        
        if memories:
            for mem in memories:
                # 1. GENERAR TÍTULO CORTO (Snippet)
                # Tomamos las primeras 5 palabras para que parezca un título
                snippet = " ".join(mem['insight_content'].split()[:5])
                if len(snippet) < len(mem['insight_content']): snippet += "..."
                
                # 2. RENDERIZADO VISUAL
                # Usamos el emoji de pin en el expander para simular el ícono
                with st.expander(f"📌 {snippet}", expanded=False):
                    st.caption(f"📅 {mem['created_at'][:10]} | {mem['project_context']}")
                    st.write(mem['insight_content'])
                    
                    # Botón de borrar discreto
                    if st.button("Eliminar", key=f"del_mem_{mem['id']}", use_container_width=True):
                        delete_insight(mem['id'])
                        st.rerun()
        else:
            st.caption("No hay insights guardados.")
    
    # --- ÁREA PRINCIPAL ---
    st.subheader("Chat de Consulta Directa")
    
    # 1. VALIDACIÓN INICIAL
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
            
            # --- BARRA DE ACCIONES DEL ASISTENTE (FEEDBACK + PIN) ---
            if msg['role'] == "Asistente":
                # Usamos columnas para alinear los iconos a la derecha o izquierda
                # Estructura: [Feedback (Left)] ....... [Pin (Right)]
                c_feed, c_spacer, c_pin = st.columns([2, 6, 1])
                
                with c_feed:
                    if 'query_id' in msg:
                        rating = st.feedback("thumbs", key=f"feed_{msg.get('query_id', idx)}")
                        if rating is not None:
                            score = 1 if rating == 1 else -1
                            update_query_rating(msg['query_id'], score)
                
                with c_pin:
                    # BOTÓN PIN MINIMALISTA (Solo Icono)
                    # help="Guardar en bitácora" aparece al pasar el mouse
                    with st.popover("📌", use_container_width=False, help="Guardar hallazgo"):
                        st.markdown("**¿Guardar en Bitácora?**")
                        if st.button("Confirmar", key=f"save_mem_{idx}"):
                            if save_project_insight(msg['message']):
                                st.toast("✅ Guardado en Bitácora")
                                st.rerun() 

    # 4. GESTIÓN DE INPUT
    prompt_to_process = None
    
    # A. Botones de Sugerencia
    if selected_files and "chat_suggestions" in st.session_state.mode_state:
        suggestions = st.session_state.mode_state.get("chat_suggestions", [])
        if suggestions:
            st.write("") 
            st.caption("🤔 **Profundizar:**")
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
        if "chat_suggestions" in st.session_state.mode_state:
            del st.session_state.mode_state["chat_suggestions"]
            
        st.session_state.mode_state["chat_history"].append({"role": "Usuario", "message": prompt_to_process})
        with st.chat_message("Usuario", avatar="👤"): 
            st.markdown(prompt_to_process)
            
        query_limit = st.session_state.plan_features.get('chat_queries_per_day', 0)
        current_queries = get_daily_usage(st.session_state.user, c.MODE_CHAT)
        
        if current_queries >= query_limit and query_limit != float('inf'): 
            st.error(f"Límite de {int(query_limit)} consultas diarias alcanzado."); return
            
        with st.chat_message("Asistente", avatar="✨"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Pensando...")
            
            # Contexto + Memoria
            relevant_info = get_relevant_info(db, prompt_to_process, selected_files)
            memory_list = get_project_memory()
            memory_text = "\n".join([f"- {m['insight_content']}" for m in memory_list])
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.mode_state["chat_history"][-10:])
            
            grounded_prompt = get_grounded_chat_prompt(conversation_history, relevant_info, long_term_memory=memory_text)
            
            response = call_gemini_api(grounded_prompt)
            
            if response: 
                message_placeholder.markdown(response)
                
                try:
                    prompt_followup = get_followup_suggestions_prompt(response)
                    resp_sugg = call_gemini_api(prompt_followup, generation_config_override={"response_mime_type": "application/json"})
                    if resp_sugg:
                        new_suggestions = json.loads(clean_gemini_json(resp_sugg))
                        st.session_state.mode_state["chat_suggestions"] = new_suggestions
                except: st.session_state.mode_state["chat_suggestions"] = []

                try:
                    res_log = log_query_event(prompt_to_process, mode=c.MODE_CHAT)
                    query_id = res_log if res_log else f"temp_{len(st.session_state.mode_state['chat_history'])}"
                except: query_id = None

                st.session_state.mode_state["chat_history"].append({
                    "role": "Asistente", 
                    "message": response,
                    "query_id": query_id
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
            if pdf_bytes: 
                st.download_button("📥 PDF", data=pdf_bytes, file_name="chat.pdf", mime="application/pdf", use_container_width=True)
        with col2: 
            def clean_all():
                reset_chat_workflow()
                if "chat_suggestions" in st.session_state.mode_state:
                    del st.session_state.mode_state["chat_suggestions"]
            st.button("🗑️ Limpiar", on_click=clean_all, key="new_grounded_chat_btn", use_container_width=True)
