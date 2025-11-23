import streamlit as st
import json
from utils import get_relevant_info, clean_gemini_json
from services.gemini_api import call_gemini_api, call_gemini_stream
from prompts import get_persona_generation_prompt, get_persona_chat_instruction
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

def synthetic_users_mode(db, selected_files):
    st.subheader("👥 Perfil Sintético")
    st.markdown("Simula conversaciones con perfiles de consumidor generados a partir de tus datos reales.")
    
    # 1. CONFIGURACIÓN DEL PERFIL
    # Se expande automáticamente si NO hay un perfil generado
    show_config = "synthetic_persona_data" not in st.session_state.mode_state
    
    with st.expander("⚙️ Configurar Perfil Sintético", expanded=show_config):
        segment_name = st.text_input("Nombre del Segmento a simular:", placeholder="Ej: Compradores sensibles al precio, Mamás primerizas...")
        
        if st.button("Generar ADN del Perfil", type="primary", width='stretch'):
            if not segment_name: st.warning("Define un segmento."); return
            
            with st.spinner("Analizando datos y construyendo psique del usuario..."):
                # Buscar datos que soporten este perfil
                context = get_relevant_info(db, segment_name, selected_files)
                if not context: st.error("No hay datos suficientes en los archivos seleccionados."); return
                
                # Generar ficha
                prompt = get_persona_generation_prompt(segment_name, context)
                resp = call_gemini_api(prompt, generation_config_override={"response_mime_type": "application/json"})
                
                try:
                    clean_resp = clean_gemini_json(resp)
                    persona_data = json.loads(clean_resp)
                    st.session_state.mode_state["synthetic_persona_data"] = persona_data
                    st.session_state.mode_state["synthetic_chat_history"] = [] # Reset chat
                    st.rerun()
                except Exception as e:
                    st.error(f"Error creando perfil: {e}")

    # 2. VISUALIZACIÓN DEL PERFIL Y CHAT
    if "synthetic_persona_data" in st.session_state.mode_state:
        p = st.session_state.mode_state["synthetic_persona_data"]
        
        # Tarjeta de identidad
        st.divider()
        col_img, col_info = st.columns([1, 3])
        with col_img:
            st.markdown(f"<div style='font-size: 80px; text-align: center;'>👤</div>", unsafe_allow_html=True)
        with col_info:
            st.markdown(f"### {p.get('nombre')}")
            st.caption(f"{p.get('edad')} | {p.get('ocupacion')}")
            st.info(f"**Bio:** {p.get('bio_breve')}")
            
        with st.expander("Ver detalles psicológicos"):
            c1, c2 = st.columns(2)
            c1.write("**Dolores:**"); c1.write(p.get('dolores_principales'))
            c2.write("**Motivadores:**"); c2.write(p.get('motivadores_compra'))
            st.write(f"**Estilo:** {p.get('estilo_comunicacion')}")

        # 3. INTERFAZ DE CHAT (ENTREVISTA)
        st.divider()
        st.markdown(f"#### 💬 Entrevista a {p.get('nombre')}")
        
        # Historial
        if "synthetic_chat_history" not in st.session_state.mode_state:
            st.session_state.mode_state["synthetic_chat_history"] = []
            
        for msg in st.session_state.mode_state["synthetic_chat_history"]:
            role = msg['role']
            name = "Entrevistador" if role == "user" else p.get('nombre')
            avatar = "🎤" if role == "user" else "👤"
            with st.chat_message(name, avatar=avatar):
                st.write(msg['content'])

        # Input
        user_question = st.chat_input(f"Hazle una pregunta a {p.get('nombre')}...")
        
        if user_question:
            # Guardar pregunta
            st.session_state.mode_state["synthetic_chat_history"].append({"role": "user", "content": user_question})
            with st.chat_message("Entrevistador", avatar="🎤"):
                st.write(user_question)
            
            # Generar respuesta "En Personaje"
            with st.chat_message(p.get('nombre'), avatar="👤"):
                with st.spinner(f"{p.get('nombre')} está pensando..."):
                    acting_prompt = get_persona_chat_instruction(p, user_question)
                    
                    stream = call_gemini_stream(acting_prompt)
                    if stream:
                        response = st.write_stream(stream)
                        st.session_state.mode_state["synthetic_chat_history"].append({"role": "assistant", "content": response})
                        st.rerun() # Rerun para actualizar botones de descarga

        # --- SECCIÓN DE ACCIONES Y CONTROL ---
        st.divider()
        c1, c2, c3 = st.columns(3)
        
        # Botón 1: Descargar (Solo si hay chat)
        with c1:
            if st.session_state.mode_state["synthetic_chat_history"]:
                chat_content = f"# Entrevista con Perfil Sintético: {p.get('nombre')}\n\n"
                chat_content += f"**Perfil:** {p.get('edad')}, {p.get('ocupacion')}\n\n---\n\n"
                for m in st.session_state.mode_state["synthetic_chat_history"]:
                    role_label = "Entrevistador" if m['role'] == 'user' else p.get('nombre')
                    chat_content += f"**{role_label}:** {m['content']}\n\n"
                
                pdf_bytes = generate_pdf_html(chat_content, title=f"Entrevista - {p.get('nombre')}", banner_path=banner_file)
                if pdf_bytes:
                    st.download_button("📄 Descargar PDF", data=pdf_bytes, file_name=f"entrevista_{p.get('nombre')}.pdf", width='stretch')
            else:
                st.write("") # Espacio vacío para mantener alineación

        # Botón 2: Reiniciar Chat (Mantiene perfil, borra mensajes)
        with c2:
            if st.session_state.mode_state["synthetic_chat_history"]:
                if st.button("🔄 Reiniciar Chat", width='stretch', help="Borra la conversación actual pero mantiene al personaje"):
                    st.session_state.mode_state["synthetic_chat_history"] = []
                    st.rerun()

        # Botón 3: Nuevo Perfil (Borra todo y vuelve al inicio) - NUEVO
        with c3:
            if st.button("✨ Crear Nuevo Perfil", width='stretch', type="secondary", help="Borra el personaje actual para crear uno diferente"):
                st.session_state.mode_state.pop("synthetic_persona_data", None)
                st.session_state.mode_state.pop("synthetic_chat_history", None)
                st.rerun()
