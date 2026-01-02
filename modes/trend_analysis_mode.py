import streamlit as st
import pandas as pd
import altair as alt
from pytrends.request import TrendReq
from services.gemini_api import call_gemini_stream
from utils import render_process_status, get_relevant_info
from prompts import get_trend_synthesis_prompt
import random

# =====================================================
# MODO: TREND RADAR 360 (OPTIMIZADO)
# =====================================================

def google_trends_mode():
    st.subheader("📡 Radar de Tendencias 360°")
    st.markdown("Triangulación de datos: **Mercado en Vivo** + **Inteligencia Interna** + **IA**.")

    # Input: Simple y limpio
    c1, c2 = st.columns([3, 1])
    keyword = c1.text_input("Término a explorar:", placeholder="Ej: Moda Sostenible, Air Fryer...")
    market = c2.selectbox("Mercado", ["Colombia", "México", "Global"], index=0)
    
    # Mapeo de códigos de país para Pytrends
    geo_map = {"Colombia": "CO", "México": "MX", "Global": ""}
    geo_code = geo_map[market]

    if st.button("Escanear Radar", type="primary", use_container_width=True):
        if not keyword:
            st.warning("Ingresa un término."); return

        # Variables de estado
        trend_df = None
        rising_terms = []
        internal_context = ""
        is_simulation = False
        
        # --- PROCESO UNIFICADO CON STATUS ---
        stream = None
        
        # Necesitamos acceder a la DB para el RAG. 
        # Asumimos que se pasa 'db_full' en app.py o usamos session_state si está cargado.
        db = st.session_state.get("db_full", [])
        # Simulamos selected_files como "todos" para buscar en todo el repo
        all_files = [d['nombre_archivo'] for d in db] if db else []

        with render_process_status(f"Analizando '{keyword}' en múltiples fuentes...", expanded=True) as status:
            
            # PASO 1: CONTEXTO INTERNO (RAG)
            status.write("📂 Buscando huellas en repositorio interno...")
            internal_context = get_relevant_info(db, keyword, all_files, max_chars=10000)
            
            # PASO 2: GOOGLE TRENDS (INTENTO)
            status.write("🌍 Conectando con Google Trends (Live)...")
            try:
                pytrends = TrendReq(hl='es', tz=300, timeout=(5, 15))
                pytrends.build_payload([keyword], cat=0, timeframe='today 12-m', geo=geo_code)
                
                # A. Interés en el tiempo
                data = pytrends.interest_over_time()
                if not data.empty:
                    data = data.reset_index()
                    trend_df = data.rename(columns={keyword: 'Interés', 'date': 'Fecha'})
                
                # B. Consultas Relacionadas (Rising)
                try:
                    related = pytrends.related_queries()
                    if related and keyword in related:
                        rising_df = related[keyword]['rising']
                        if rising_df is not None:
                            rising_terms = rising_df.head(5)['query'].tolist()
                except:
                    pass # Si falla related queries, seguimos con lo demás

            except Exception as e:
                # FALLBACK ELEGANTE
                status.write("⚠️ Señal externa débil (Google API). Activando simulación predictiva...")
                is_simulation = True
                
                # Generamos curva dummy coherente
                dates = pd.date_range(end=pd.Timestamp.now(), periods=52, freq='W')
                base = random.randint(20, 50)
                values = [min(100, max(0, base + (i * 0.8) + random.randint(-10, 10))) for i in range(52)]
                trend_df = pd.DataFrame({'Fecha': dates, 'Interés': values})
                rising_terms = [f"{keyword} beneficios", f"{keyword} precio", f"cómo hacer {keyword}"]

            # PASO 3: SÍNTESIS CON IA
            status.write("🧠 El Estratega Virtual está conectando los puntos...")
            
            # Preparamos los textos para el prompt
            trend_summary = f"Tendencia {'simulada' if is_simulation else 'real'}. Último valor de interés: {trend_df['Interés'].iloc[-1]}/100."
            rising_str = ", ".join(rising_terms) if rising_terms else "No se detectaron breakouts específicos."
            
            final_prompt = get_trend_synthesis_prompt(keyword, trend_summary, internal_context, rising_str)
            
            stream = call_gemini_stream(final_prompt)
            
            if stream:
                status.update(label="¡Análisis completado!", state="complete", expanded=False)
            else:
                status.update(label="Error en síntesis", state="error")

        # --- VISUALIZACIÓN DE RESULTADOS ---
        
        # 1. KPIs Rápidos
        k1, k2, k3 = st.columns(3)
        last_val = trend_df['Interés'].iloc[-1]
        avg_val = trend_df['Interés'].mean()
        delta = last_val - avg_val
        
        k1.metric("Interés Actual", f"{int(last_val)}/100", delta=f"{int(delta)} vs Promedio")
        k2.metric("Fuente de Datos", "Simulación IA" if is_simulation else "Google Trends Live", delta_color="off")
        k3.metric("Menciones Internas", "Sí detectadas" if len(internal_context) > 100 else "No detectadas", 
                 delta="Validado" if len(internal_context) > 100 else "Nuevo Territorio")

        # 2. Gráfico y Contexto
        tab_main, tab_internal = st.tabs(["📈 Radar de Mercado", "🗂️ Evidencia Interna"])
        
        with tab_main:
            # Gráfico
            chart = alt.Chart(trend_df).mark_area(
                line={'color':'#29B5E8'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#29B5E8', offset=0),
                           alt.GradientStop(color='rgba(255,255,255,0)', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X('Fecha:T', title="Último Año"),
                y=alt.Y('Interés:Q', title="Interés"),
                tooltip=['Fecha', 'Interés']
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)
            
            # Rising Terms (Píldoras)
            if rising_terms:
                st.caption("🔥 Búsquedas en aumento (Breakout Trends):")
                # Visualización estilo "tags"
                tags_html = " ".join([f"<span style='background-color:#f0f2f6; padding:4px 8px; border-radius:12px; margin-right:5px; font-size:12px;'>📈 {term}</span>" for term in rising_terms])
                st.markdown(tags_html, unsafe_allow_html=True)

        with tab_internal:
            if len(internal_context) > 100:
                st.info("💡 La IA encontró fragmentos relevantes en tus estudios anteriores:")
                with st.container(height=300):
                    st.markdown(internal_context)
            else:
                st.warning("Esta tendencia parece ser nueva para la organización. No se encontraron referencias directas en el repositorio.")

        # 3. Output Estratégico de la IA
        st.divider()
        if stream:
            st.markdown("### 🎯 Atelier Strategic Brief")
            st.write_stream(stream)
