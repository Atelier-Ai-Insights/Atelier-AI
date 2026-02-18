import streamlit as st
import time
import constants as c

# --- COMPONENTES UNIFICADOS ---
from components.chat_interface import render_chat_history, handle_chat_interaction
from components.export_utils import render_final_actions

# 1. Servicios IA
try:
    from services.gemini_api import call_gemini_stream
    gemini_available = True
except ImportError:
    gemini_available = False
    def call_gemini_stream(prompt): return None

# 2. Utilidades
try:
    from utils import get_relevant_info
except ImportError:
    def get_relevant_info(db, q, f): return ""

# 3. Base de Datos y Prompts
try:
    from services.supabase_db import log_query_event
    from prompts import get_ideation_prompt 
except ImportError:
    def log_query_event(q, m): pass
    def get_ideation_prompt(h, r): return ""

def ideacion_mode(db, selected_files):
    """
    Modo Ideación Estratégica: Implementa el estándar de invisibilidad 
    y trazabilidad sistemática de fuentes.
    """
    st.subheader("Ideación Estratégica")
    st.caption("Brainstorming creativo fundamentado en datos del repositorio.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "ideation_history" not in st.session_state.mode_state:
        st.session_state.mode_state["ideation_history"] = []

    # 2. RENDERIZAR HISTORIAL (Limpio visualmente)
    # Oculta metadatos técnicos mientras mantiene las referencias vivas.
    render_chat_history(st.session_state.mode_state["ideation_history"], source_mode="ideation")

    # 3. INTERACCIÓN DEL USUARIO
    if user_input := st.chat_input("Escribe un desafío creativo..."):

        def ideation_generator():
            status_box = st.empty()
            with status_box.status("Activando motor creativo...", expanded=True) as status:
                if not gemini_available:
                    status.update(label="IA no disponible", state="error")
                    return iter(["Error: IA no disponible."])

                # Paso 1: RAG
                status.write("Conectando con la base de conocimiento...")
                relevant_info = get_relevant_info(db, user_input, selected_files)
                
                # Paso 2: Contexto y Pensamiento Lateral
                status.write("Analizando contexto de la sesión...")
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["ideation_history"][-3:]])
                prompt = get_ideation_prompt(hist_str, relevant_info)
                
                # Paso 3: Generación Stream
                status.write("Aplicando pensamiento lateral...")
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="¡Ideas generadas!", state="complete", expanded=False)
                    time.sleep(0.7)
                    status_box.empty()
                    return stream
                else:
                    status.update(label="Error al generar", state="error")
                    return iter(["Error al conectar con el motor creativo."])

        # Delegamos al componente visual para guardado íntegro.
        handle_chat_interaction(
            prompt=user_input,
            response_generator_func=ideation_generator,
            history_key="ideation_history",
            source_mode="ideation",
            on_generation_success=lambda resp: log_query_event(f"Ideación: {user_input[:50]}", mode=c.MODE_IDEATION)
        )

    # 4. ACCIONES FINALES (Barra Maestra Unificada)
    if st.session_state.mode_state["ideation_history"]:
        # Construimos el contenido acumulado preservando metadatos para el modal.
        full_content = ""
        for m in st.session_state.mode_state["ideation_history"]:
            role_label = "Usuario" if m["role"] == "user" else "Atelier AI"
            full_content += f"### {role_label}\n{m['content']}\n\n"

        def reset_ideation_workflow():
            st.session_state.mode_state["ideation_history"] = []
            st.rerun()

        # Renderiza Feedback, Referencias (con filtrado único) y Exportaciones.
        render_final_actions(
            content=full_content,
            title="Sesion_Ideacion_Estrategica",
            mode_key="ideation_actions",
            on_reset_func=reset_ideation_workflow
        )
