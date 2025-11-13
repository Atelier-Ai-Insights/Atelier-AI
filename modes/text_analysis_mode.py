# ... (dentro de show_text_project_analyzer) ...
    with tab_autocode:
        st.header("Auto-Codificación")
        
        if "autocode_result" in st.session_state.mode_state:
            # ... (código de visualización y descarga igual que antes) ...
            st.markdown("### Reporte de Temas Generado")
            st.markdown(st.session_state.mode_state["autocode_result"])
            # ... (botones) ...
        
        else:
            st.markdown("Genera un reporte de temas clave.")
            main_topic = st.text_input("Tema principal:", key="autocode_topic")

            if st.button("Analizar Temas", use_container_width=True, type="primary"):
                if not main_topic.strip(): st.warning("Define el tema."); return
                
                with st.spinner("Analizando temas emergentes..."):
                    prompt = get_autocode_prompt(summary_context, main_topic)
                    
                    # --- STREAMING ---
                    stream = call_gemini_stream(prompt)

                    if stream:
                        st.markdown("### Reporte en progreso...")
                        response = st.write_stream(stream)
                        
                        st.session_state.mode_state["autocode_result"] = response
                        log_query_event(f"Auto-codificación: {main_topic}", mode=f"{c.MODE_TEXT_ANALYSIS} (Autocode)")
                        st.rerun()
                    else:
                        st.error("Error al generar reporte.")
