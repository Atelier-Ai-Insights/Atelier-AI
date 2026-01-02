import streamlit as st
import json
from utils import get_relevant_info, reset_chat_workflow, clean_gemini_json
from services.gemini_api import call_gemini_api
from services.supabase_db import get_daily_usage, log_query_event, supabase 
from services.memory_service import save_project_insight, get_project_memory, delete_insight # <--- NUEVO SERVICIO
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
# MODO: CHAT DE CONSULTA DIRECTA (CON MEMORIA)
# =====================================================

def grounded_chat_mode(db, selected_files):
    
    # --- BARRA LATERAL: BITÁCORA DE PROYECTO ---
    with st.sidebar:
        st.divider()
        st.markdown("### 🧠 Bitácora del Proyecto")
        memories = get_project_memory()
        
        if memories:
            for mem in memories:
                with st.expander(f"📌 {mem['created_at'][:10]}...", expanded=False):
                    st.caption(f"Contexto: {mem['project_context']}")
                    st.write(mem['insight_content'])
                    if st.button("Borrar", key=f"del_mem_{mem['id']}"):
                        delete_insight(mem['id'])
                        st.rerun()
        else:
            st.caption("No hay insights guardados para este proyecto aún.")
    
    # --- ÁREA PRINCIPAL ---
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

    # 3. MOSTRAR HISTORIAL E INTERACCIONES
    for idx, msg in enumerate(st.session_state.mode_state["chat_history"]):
        with st.chat_message(msg['role'], avatar="✨" if msg['role'] == "Asistente" else "👤"): 
            st.markdown(msg['message'])
            
            # SOLO EN MENSAJES DEL ASISTENTE: Feedback y Guardar Memoria
            if msg['role'] == "Asistente":
                c1, c2 = st.columns([1, 10])
                
                # Botón de Feedback
                with c1:
                    if 'query_id' in msg:
                        rating = st.feedback("thumbs", key=f"feed_{msg.get('query_id', idx)}")
                        if rating is not None:
                            score = 1 if rating == 1 else -1
                            update_query_rating(msg['query_id'], score)
                
                # Botón de Guardar en Bitácora (Pin)
                with c2:
                    # Usamos un popover para confirmar el guardado
                    with st.popover("📌 Pin Insight"):
                        st.markdown("**¿Guardar este hallazgo en la Bitácora del Proyecto?**")
                        st.caption("La IA recordará esto en futuras conversaciones.")
                        if st.button("Confirmar Guardado", key=f"save_mem_{idx}"):
                            if save_project_insight(msg['message']):
                                st.toast("✅ Insight guardado en la memoria del proyecto.")
                                st.rerun() # Recargar para ver en sidebar

    # 4. GESTIÓN DE INPUT
    prompt_to_process = None
    
    # A. Botones de Sugerencia (Contextuales)
    if selected_files and "chat_suggestions" in st.session_state.mode_state:
        suggestions = st.session_state.mode_state.get("chat_suggestions", [])
        if suggestions:
            st.write("") 
            st.caption("🤔 **Profundizar en el tema:**")
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
            
            # --- CONSTRUCCIÓN DEL CONTEXTO CON MEMORIA ---
            # 1. Obtenemos Info de PDFS
            relevant_info = get_relevant_info(db, prompt_to_process, selected_files)
            
            # 2. Obtenemos Info de BITÁCORA (Memoria a Largo Plazo)
            memory_list = get_project_memory()
            memory_text = "\n".join([f"- {m['insight_content']}" for m in memory_list])
            
            # 3. Historial Corto
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.mode_state["chat_history"][-10:])
            
            # 4. Llamada al Prompt Actualizado
            grounded_prompt = get_grounded_chat_prompt(conversation_history, relevant_info, long_term_memory=memory_text)
            
            response = call_gemini_api(grounded_prompt)
            
            if response: 
                message_placeholder.markdown(response)
                
                # Generar Sugerencias Follow-up
                try:
                    prompt_followup = get_followup_suggestions_prompt(response)
                    resp_sugg = call_gemini_api(prompt_followup, generation_config_override={"response_mime_type": "application/json"})
                    if resp_sugg:
                        new_suggestions = json.loads(clean_gemini_json(resp_sugg))
                        st.session_state.mode_state["chat_suggestions"] = new_suggestions
                except: st.session_state.mode_state["chat_suggestions"] = []

                # Logs
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
                st.download_button("📥 Descargar Chat PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf", width='stretch')
        with col2: 
            def clean_all():
                reset_chat_workflow()
                if "chat_suggestions" in st.session_state.mode_state:
                    del st.session_state.mode_state["chat_suggestions"]
            st.button("🗑️ Nueva Conversación", on_click=clean_all, key="new_grounded_chat_btn", width='stretch')
