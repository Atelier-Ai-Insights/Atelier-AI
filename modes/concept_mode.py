import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event

# =====================================================
# MODO: GENERACIÓN DE CONCEPTOS
# =====================================================

def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos")
    st.markdown("Genera concepto de producto/servicio a partir de idea y hallazgos.")
    
    if "generated_concept" in st.session_state:
        st.markdown("---")
        st.markdown("### Concepto Generado")
        st.markdown(st.session_state.generated_concept)
        if st.button("Generar nuevo concepto", use_container_width=True): 
            st.session_state.pop("generated_concept")
            st.rerun()
    else:
        product_idea = st.text_area("Describe tu idea:", height=150, placeholder="Ej: Snack saludable...")
        
        if st.button("Generar Concepto", use_container_width=True):
            if not product_idea.strip(): 
                st.warning("Describe tu idea.")
                return
                
            with st.spinner("Generando concepto..."):
                context_info = get_relevant_info(db, product_idea, selected_files)
                prompt = (
                    f"**Tarea:** Estratega Mkt/Innovación. Desarrolla concepto estructurado a partir de 'Idea' y 'Contexto'.\n\n"
                    f"**Idea:**\n\"{product_idea}\"\n\n"
                    f"**Contexto (Hallazgos):**\n\"{context_info}\"\n\n"
                    f"**Instrucciones:**\nGenera Markdown con estructura exacta. Basa respuestas en contexto. Sé claro, conciso, accionable.\n\n"
                    "---\n\n"
                    "### 1. Necesidad Consumidor\n* Identifica tensiones/deseos clave del contexto. Conecta con oportunidad.\n\n"
                    "### 2. Descripción Producto/Servicio\n* Basado en Idea y enriquecido por Contexto. Características, funcionamiento.\n\n"
                    "### 3. Beneficios Clave (3-4)\n* Responde a necesidad (Pto 1). Sustentado en Contexto. Funcional/Racional/Emocional.\n\n"
                    "### 4. Conceptos para Evaluar (2 Opc.)\n"
                    "* **Opción A:**\n"
                    "    * **Insight:** (Dolor + Deseo. Basado en contexto).\n"
                    "    * **What:** (Características/Beneficios. Basado en contexto/descripción).\n"
                    "    * **RTB:** (¿Por qué creíble? Basado en contexto).\n"
                    "    * **Claim:** (Esencia memorable).\n\n"
                    "* **Opción B:** (Alternativa)\n"
                    "    * **Insight:**\n"
                    "    * **What:**\n"
                    "    * **RTB:**\n"
                    "    * **Claim:**"
                )
                
                response = call_gemini_api(prompt)
                
                if response: 
                    st.session_state.generated_concept = response
                    log_query_event(product_idea, mode="Generación de conceptos")
                    st.rerun()
                else: 
                    st.error("No se pudo generar concepto.")
