import streamlit as st
import json
from utils import get_relevant_info, reset_chat_workflow, clean_gemini_json
from services.gemini_api import call_gemini_api
from services.supabase_db import get_daily_usage, log_query_event, supabase 
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_grounded_chat_prompt, get_chat_suggestions_prompt
import constants as c 

# =====================================================
# FUNCIONES AUXILIARES
# =====================================================
def update_query_rating(query_id, rating):
    try:
        supabase.table("queries").update({"rating": rating}).eq("id", query_id).execute()
    except Exception as e: print(f"Error rating: {e}")

def get_file_sneak_peek(db, selected_files, char_limit=4000):
    """
    Extrae los primeros N caracteres de los archivos seleccionados para dar contexto a las sugerencias.
    """
    preview_text = ""
    sel_set = set(selected_files)
    
    found_count = 0
    for doc in db:
        if doc.get('nombre_archivo') in sel_set:
            grupos = doc.get("grupos", [])
            if grupos:
                text_chunk = str(grupos[0].get('contenido_texto', ''))[:1000] 
                preview_text += f"\n[Doc: {doc.get('nombre_archivo')}]\n{text_chunk}...\n"
                found_count += 1
            if found_count >= 3: break
            
    if len(preview_text) > char_limit:
        return preview_text[:char_limit]
    return preview_text

# =====================================================
# MODO: CHAT DE CONSULTA DIRECTA (GROUNDED)
# =====================================================

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    
    # 1. VALIDACIÓN INICIAL DE FILTROS
    # Si no hay archivos seleccionados, mostramos aviso y detenemos sugerencias
    if not selected_files:
        st.info("👈 **Para comenzar:** Selecciona una Marca, Año y Proyecto en el menú lateral.")
        st.caption("El chat se activará cuando hayas definido qué documentos analizar.")
        
        # Inicializamos historial vacío para que no rompa
        if "chat_history" not in st.session_state.mode_state:
            st.session_state.mode_state["chat_history"] = []
    else:
        st.markdown(f"Analizando **{len(selected_files)} documento(s)** seleccionados.")

    # 2. INICIALIZACIÓN DE ESTADO
    if "chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["chat_history"] = []
    
    # 3. GENERACIÓN DE SUGERENCIAS (SOLO SI HAY ARCHIVOS Y CHAT VACÍO)
    if selected_files and not st.session_state.mode_state["chat_history"]:
        if "chat_suggestions" not in st.session_state.mode_state:
            with st.spinner("🧠 Leyendo documentos para sugerir preguntas estratégicas..."):
                try:
                    context_preview = get_file_sneak_peek(db, selected_files)
                    
                    if context_preview:
                        prompt_sugg = get_chat_suggestions_prompt(context_preview)
                        resp_sugg = call_gemini_api(prompt_sugg, generation_config_override={"response_mime_type": "application/json"})
                        if resp_sugg:
                            suggestions = json.loads(clean_gemini_json(resp_sugg))
                            st.session_state.mode_state["chat_suggestions"] = suggestions
                    else:
                        st.session_state.mode_state["chat_suggestions"] = []
                except Exception as e:
                    print(f"Error sugiriendo: {e}")
                    st.session_state.mode_state["chat_suggestions"] = []

    # 4. MOSTRAR HISTORIAL
    for msg in st.session_state.mode_state["chat_history"]:
        with st.chat_message(msg['role'], avatar="✨" if msg['role'] == "Asistente" else "👤"): 
            st.markdown(msg['message'])
            if msg['role'] == "Asistente" and 'query_id' in msg:
                rating = st.feedback("thumbs", key=f"feed_{msg['query_id']}")
                if rating is not None:
                    score = 1 if rating == 1 else -1
                    update_query_rating(msg['query_id'], score)

    # 5. GESTIÓN DE INPUT
    prompt_to_process = None
    
    # A. Botones de Sugerencia (Verticales y Abajo)
    # Solo se muestran si: 1) Hay archivos, 2) Chat vacío, 3) Hay sugerencias generadas
    if selected_files and "chat_suggestions" in st.session_state.mode_state and not st.session_state.mode_state["chat_history"]:
        suggestions = st.session_state.mode_state.get("chat_suggestions", [])
        if suggestions:
            st.write("") # Espaciador
            st.markdown("##### 💡 Preguntas sugeridas para estos documentos:")
            
            # CAMBIO: Iteración vertical simple (una debajo de otra)
            for i, sugg in enumerate(suggestions):
                # Use container width hace que parezcan opciones de menú móvil, muy limpio
                if st.button(f"👉 {sugg}", key=f"sugg_btn_{i}", use_container_width=True):
                    prompt_to_process = sugg

    # B. Input Usuario (Siempre visible, pero deshabilitado si no hay archivos opcionalmente)
    user_input = st.chat_input("Escribe tu pregunta...", disabled=not selected_files)
    if user_input:
        prompt_to_process = user_input

    # 6. PROCESAMIENTO
    if prompt_to_process and selected_files:
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
                
    # 7. EXPORTACIÓN Y LIMPIEZA
    if st.session_state.mode_state["chat_history"]:
        st.divider()
        col1, col2 = st.columns([1,1])
        with col1:
            chat_content_raw = "\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.mode_state["chat_history"])
            pdf_bytes = generate_pdf_html(chat_content_raw.replace("](#)", "]"), title="Historial Consulta", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button("📥 Descargar Chat PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf", width='stretch')
        with col2: 
            st.button("🗑️ Nueva Conversación", on_click=reset_chat_workflow, key="new_grounded_chat_btn", width='stretch')
