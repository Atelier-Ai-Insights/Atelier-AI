import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
# --- ¡IMPORTACIÓN ACTUALIZADA! ---
from services.supabase_db import log_query_event, log_query_feedback
from prompts import get_idea_eval_prompt 

# =====================================================
# MODO: EVALUACIÓN DE PRE-IDEAS
# =====================================================

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas")
    st.markdown("Evalúa potencial de idea contra hallazgos.")

    # --- ¡CAMBIO 1: El Callback ahora SOLO acepta 'feedback'! ---
    def idea_feedback_callback(feedback):
        # Obtenemos el key que pasamos a st.feedback
        key = feedback['key']
        # El key tiene el formato "feedback_QUERYID". Extraemos el ID.
        query_id = key.split("feedback_")[-1] # Obtenemos la parte del ID

        if query_id:
            # Usar .get() para seguridad y score=0 para 'thumbs_down'
            score = 1 if feedback.get('score') == 'thumbs_up' else 0
            log_query_feedback(query_id, score)
            st.toast("¡Gracias por tu feedback!")
            # Oculta los botones después de votar
            st.session_state.voted_on_last_idea = True
        else:
            st.toast("Error: No se encontró el ID de la consulta.")
    # --- FIN DEL CALLBACK ---
    
    if "evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### Evaluación")
        st.markdown(st.session_state.evaluation_result)

        # --- ¡SECCIÓN DE FEEDBACK CORREGIDA! ---
        query_id = st.session_state.get("last_idea_query_id")
        if query_id and not st.session_state.get("voted_on_last_idea", False):
            # CAMBIO 2: Usar st.feedback (nombre oficial)
            st.feedback(
                key=f"feedback_{query_id}", # CAMBIO 3: La key DEBE contener el ID
                on_submit=idea_feedback_callback
                # Se elimina: args=(query_id,)
            )
        # --- FIN DE LA SECCIÓN DE FEEDBACK ---

        if st.button("Evaluar otra idea", use_container_width=True): 
            del st.session_state["evaluation_result"]
            # Limpiamos las variables de feedback
            st.session_state.pop("last_idea_query_id", None)
            st.session_state.pop("voted_on_last_idea", None)
            st.rerun() # Este rerun es correcto
    else:
        idea_input = st.text_area("Describe la idea a evaluar:", height=150, placeholder="Ej: Yogures con probióticos...")
        
        if st.button("Evaluar Idea", use_container_width=True):
            if not idea_input.strip(): 
                st.warning("Describe una idea.")
                return
                
            with st.spinner("Evaluando potencial..."):
                context_info = get_relevant_info(db, idea_input, selected_files)
                
                prompt = get_idea_eval_prompt(idea_input, context_info)
                
                response = call_gemini_api(prompt)
                
                if response: 
                    st.session_state.evaluation_result = response
                    
                    query_id = log_query_event(idea_input, mode="Evaluación de Idea")
                    st.session_state["last_idea_query_id"] = query_id
                    st.session_state["voted_on_last_idea"] = False 
                    
                    st.rerun() # Este rerun es correcto para mostrar el resultado
                else: 
                    st.error("No se pudo generar evaluación.")