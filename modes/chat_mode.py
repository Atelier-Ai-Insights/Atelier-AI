import streamlit as st
import json
from utils import get_relevant_info, reset_chat_workflow, clean_gemini_json
from services.gemini_api import call_gemini_api
from services.supabase_db import get_daily_usage, log_query_event, supabase 
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_grounded_chat_prompt, get_followup_suggestions_prompt # <--- CAMBIO AQUÍ
import constants as c 

# =====================================================
# FUNCIONES AUXILIARES
# =====================================================
def update_query_rating(query_id, rating):
    try:
        supabase.table("queries").update({"rating": rating}).eq("id", query_id).execute()
    except Exception as e: print(f"Error rating: {e}")

# =====================================================
# MODO: CHAT DE CONSULTA DIRECTA (GROUNDED)
# =====================================================

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    
    # 1. VALIDACIÓN INICIAL
    if not selected_files:
        st.info("👈 **Para comenzar:** Selecciona una Marca, Año y Proyecto en el menú lateral.")
        if "chat_history" not in st.session_state.mode_state:
            st.session_state.mode_state["chat_history"] = []
    else:
        st.markdown(f"Analizando **{len(selected_files)} documento(s)** seleccionados.")

    # 2. INICIALIZACIÓN
    if "chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["chat_history"] = []
    
    # (ELIMINADO: Bloque de sugerencias iniciales "Sneak Peek")

    # 3. MOSTRAR HISTORIAL
    for msg in st.session_state.mode_state["chat_history"]:
        with st.chat_message(msg['role'], avatar="✨" if msg['role'] == "Asistente" else "👤"): 
            st.markdown(msg['message'])
            if msg['role'] == "Asistente" and 'query_id' in msg:
                rating = st.feedback("thumbs", key=f"feed_{msg['query_id']}")
                if rating is not None:
                    score = 1 if rating == 1 else -1
                    update_query_rating(msg['query_id'], score)

    # 4. GESTIÓN DE INPUT
    prompt_to_process = None
    
    # A. Botones de Sugerencia (Contextuales - Follow Up)
    # Se muestran si existen en el estado (generadas tras la última respuesta)
    if selected_files and "chat_suggestions" in st.session_state.mode_state:
        suggestions = st.session_state.mode_state.get("chat_suggestions", [])
        if suggestions:
            st.write("") # Espaciador visual
            st.caption("🤔 **Profundizar en el tema:**")
            
            # Mostramos una debajo de la otra
            for i, sugg in enumerate(suggestions):
                if st.button(f"👉 {sugg}", key=f"sugg_btn_{i}", use_container_width=True):
                    prompt_to_process = sugg
            st.write("") # Espaciador antes del input

    # B. Input Usuario
    user_input = st.chat_input("Escribe tu pregunta...", disabled=not selected_files)
    if user_input:
        prompt_to_process = user_input

    # 5. PROCESAMIENTO
    if prompt_to_process and selected_files:
        # Limpiar sugerencias viejas al hacer una nueva pregunta para no confundir
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
            
            relevant_info = get_relevant_info(db, prompt_to_process, selected_files)
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.mode_state["chat_history"][-10:])
            grounded_prompt = get_grounded_chat_prompt(conversation_history, relevant_info)
            
            response = call_gemini_api(grounded_prompt)
            
            if response: 
                message_placeholder.markdown(response)
                
                # --- GENERACIÓN DE NUEVAS SUGERENCIAS (FOLLOW-UP) ---
                # Generamos las sugerencias basadas en ESTA respuesta para el siguiente turno
                try:
                    prompt_followup = get_followup_suggestions_prompt(response)
                    # Llamada silenciosa (sin spinner que bloquee) o muy rápida
                    resp_sugg = call_gemini_api(prompt_followup, generation_config_override={"response_mime_type": "application/json"})
                    if resp_sugg:
                        new_suggestions = json.loads(clean_gemini_json(resp_sugg))
                        st.session_state.mode_state["chat_suggestions"] = new_suggestions
                except Exception as e:
                    # Si falla la sugerencia, no importa, el chat principal funcionó
                    print(f"Error generando follow-up: {e}")
                    st.session_state.mode_state["chat_suggestions"] = []

                # Guardado y Logging
                try:
                    res_log = log_query_event(prompt_to_process, mode=c.MODE_CHAT)
                    query_id = res_log if res_log else f"temp_{len(st.session_state.mode_state['chat_history'])}"
                except: query_id = None

                st.session_state.mode_state["chat_history"].append({
                    "role": "Asistente", 
                    "message": response,
                    "query_id": query_id
                })
                
                # Rerun para que aparezcan los botones de sugerencia nuevos abajo
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
                st.download_button("📥 Descargar Chat PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf", width='stretch')
        with col2: 
            # Al limpiar, también borramos sugerencias
            def clean_all():
                reset_chat_workflow()
                if "chat_suggestions" in st.session_state.mode_state:
                    del st.session_state.mode_state["chat_suggestions"]
            
            st.button("🗑️ Nueva Conversación", on_click=clean_all, key="new_grounded_chat_btn", width='stretch')
