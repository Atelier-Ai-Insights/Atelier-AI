import streamlit as st
import constants as c
from components.chat_interface import render_chat_history, handle_chat_interaction
from components.export_utils import render_final_actions
from utils import get_relevant_info, render_process_status
from services.gemini_api import call_gemini_api # O call_gemini_stream si prefieres streaming
from services.supabase_db import log_query_event
from prompts import get_idea_eval_prompt

def idea_evaluator_mode(db, selected_files):
    """
    Modo Evaluador de Ideas: Implementa el estándar de invisibilidad 
    y trazabilidad sistemática de fuentes.
    """
    st.subheader("Evaluador de Ideas")
    st.caption("Somete tu idea al juicio crítico de los datos de mercado.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "eval_history" not in st.session_state.mode_state:
        st.session_state.mode_state["eval_history"] = []

    # 2. RENDERIZAR HISTORIAL (Con limpieza visual sistemática)
    # Esta función oculta los metadatos técnicos en la UI
    render_chat_history(st.session_state.mode_state["eval_history"], source_mode="eval")

    # 3. INPUT ESTILO CHAT
    idea_input = st.chat_input("Escribe la idea que quieres evaluar...")

    if idea_input:
        def eval_generator():
            """Generador de respuesta con estado de procesamiento."""
            status_placeholder = st.empty()
            with status_placeholder.status("Analizando viabilidad estratégica...", expanded=True) as status:
                # Búsqueda RAG
                relevant = get_relevant_info(db, idea_input, selected_files)
                
                if not relevant:
                    status.update(label="Sin contexto suficiente", state="error")
                    return iter(["No encontré información en los documentos para evaluar esta idea."])
                
                status.write("Contrastando con datos de mercado...")
                prompt = get_idea_eval_prompt(idea_input, relevant)
                
                # Llamada a la IA (usamos call_gemini_api para coincidir con tu lógica original)
                response = call_gemini_api(prompt)
                
                if response:
                    status.update(label="Evaluación completada", state="complete", expanded=False)
                    status_placeholder.empty()
                    # Retornamos como iterable para compatibilidad con handle_chat_interaction
                    return iter([response])
                else:
                    status.update(label="Error en el motor de IA", state="error")
                    return iter(["Error al generar la evaluación."])

        # Procesar interacción (Guarda la respuesta completa con metadatos técnicos)
        handle_chat_interaction(
            prompt=idea_input,
            response_generator_func=eval_generator,
            history_key="eval_history",
            source_mode="eval",
            on_generation_success=lambda resp: log_query_event(f"Eval: {idea_input[:20]}", mode=c.MODE_IDEA_EVAL)
        )

    # 4. ACCIONES FINALES (Barra Maestra)
    if st.session_state.mode_state["eval_history"]:
        # Construimos el full_content preservando los metadatos invisibles
        full_content = ""
        for m in st.session_state.mode_state["eval_history"]:
            role = "Idea" if m["role"] == "user" else "Atelier AI"
            full_content += f"### {role}\n{m['content']}\n\n"

        def reset_eval_workflow():
            st.session_state.mode_state["eval_history"] = []

        # Renderiza Feedback, Referencias (Modal Numerado) y Descargas
        render_final_actions(
            content=full_content,
            title="Evaluacion_Estrategica_Atelier",
            mode_key="evaluator_mode",
            on_reset_func=reset_eval_workflow
        )
