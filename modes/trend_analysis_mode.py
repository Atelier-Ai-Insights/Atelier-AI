import streamlit as st
import pandas as pd
import altair as alt
from pytrends.request import TrendReq
from services.gemini_api import call_gemini_stream
from utils import render_process_status, get_relevant_info
from prompts import get_trend_synthesis_prompt
import random

# =====================================================
# MODO: TREND RADAR PRO (GEO + TEMAS + METRICAS)
# =====================================================

def calculate_growth(df):
    """Calcula el crecimiento porcentual entre el promedio inicial y final."""
    if df.empty or len(df) < 2: return 0
    first_half = df['Interés'].iloc[:len(df)//2].mean()
    last_half = df['Interés'].iloc[len(df)//2:].mean()
    if first_half == 0: return 100 if last_half > 0 else 0
    return ((last_half - first_half) / first_half) * 100

def google_trends_mode():
    st.subheader("📡 Radar de Tendencias Pro")
    st.markdown("Análisis multidimensional: **Tiempo + Espacio + Contexto**.")

    # --- FILTROS AVANZADOS ---
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        keyword = c1.text_input("Término:", placeholder="Ej: Ropa de Segunda, Creatina...")
        market = c2.selectbox("Mercado", ["Colombia", "México", "Global"], index=0)
        timeframe = c3.selectbox("Ventana de Tiempo", 
                                 options=["today 1-m", "today 12-m", "today 5-y"], 
                                 format_func=lambda x: "Últimos 30 días" if "1-m" in x else "Último Año" if "12-m" in x else "5 Años")

    geo_map = {"Colombia": "CO", "México": "MX", "Global": ""}
    geo_code = geo_map[market]

    if st.button("🚀 Escanear Tendencia", type="primary", use_container_width=True):
        if not keyword:
            st.warning("Ingresa un término."); return

        # Variables de estado
        trend_df = None
        geo_df = None
        related_topics = []
        rising_queries = []
        
        internal_context = ""
        is_simulation = False
        simulation_reason = ""
        
        # Acceso a DB
        db = st.session_state.get("db_full", [])
        all_files = [d['nombre_archivo'] for d in db] if db else []

        with render_process_status(f"Ejecutando análisis profundo para '{keyword}'...", expanded=True) as status:
            
            # 1. RAG INTERNO
            status.write("📂 Cruzando con repositorio interno...")
            internal_context = get_relevant_info(db, keyword, all_files, max_chars=8000)
            
            # 2. GOOGLE TRENDS API
            status.write("🌍 Extrayendo datos de Google Trends (Time & Geo)...")
            try:
                pytrends = TrendReq(hl='es', tz=300, timeout=(5, 20))
                pytrends.build_payload([keyword], cat=0, timeframe=timeframe, geo=geo_code)
                
                # A. INTERÉS EN EL TIEMPO
                data = pytrends.interest_over_time()
                if data.empty: raise ValueError("EmptyData")
                
                data = data.reset_index()
                trend_df = data.rename(columns={keyword: 'Interés', 'date': 'Fecha'})
                
                # B. INTERÉS POR REGIÓN (Nuevo)
                try:
                    status.write("🗺️ Mapeando interés regional...")
                    geo_data = pytrends.interest_by_region(resolution='REGION', inc_low_vol=True, inc_geo_code=False)
                    geo_data = geo_data[geo_data[keyword] > 0].sort_values(keyword, ascending=False).head(10)
                    if not geo_data.empty:
                        geo_df = geo_data.reset_index().rename(columns={keyword: 'Interés', 'geoName': 'Región'})
                except: pass

                # C. TEMAS Y CONSULTAS (Nuevo)
                try:
                    status.write("🔗 Analizando contexto semántico...")
                    # Queries
                    rel_queries = pytrends.related_queries()
                    if rel_queries and keyword in rel_queries:
                        r_q = rel_queries[keyword]['rising']
                        if r_q is not None: rising_queries = r_q.head(7)['query'].tolist()
                    
                    # Topics (Conceptos más amplios)
                    rel_topics = pytrends.related_topics()
                    if rel_topics and keyword in rel_topics:
                        r_t = rel_topics[keyword]['rising']
                        if r_t is not None: related_topics = r_t.head(5)['topic_title'].tolist()
                except: pass

            except Exception as e:
                # FALLBACK (Simulación)
                is_simulation = True
                if "EmptyData" in str(e):
                    simulation_reason = "Término muy específico (Nicho)."
                else:
                    simulation_reason = "Bloqueo temporal de API Google."
                
                status.write(f"⚠️ {simulation_reason} Generando proyección IA...")
                
                # Generar datos dummy
                periods = 30 if "1-m" in timeframe else 52
                freq = 'D' if "1-m" in timeframe else 'W'
                dates = pd.date_range(end=pd.Timestamp.now(), periods=periods, freq=freq)
                values = [min(100, max(0, random.randint(20, 60) + (i * 0.5) + random.randint(-10, 10))) for i in range(periods)]
                trend_df = pd.DataFrame({'Fecha': dates, 'Interés': values})
                rising_queries = [f"precio {keyword}", f"opiniones {keyword}", f"donde comprar {keyword}"]

            # 3. SÍNTESIS IA
            status.write("🧠 Generando Brief Estratégico...")
            
            # Preparar textos para el prompt
            trend_txt = f"Tendencia {'simulada' if is_simulation else 'real'}. Valor actual: {trend_df['Interés'].iloc[-1]}."
            geo_txt = ", ".join([f"{r['Región']} ({r['Interés']})" for i, r in geo_df.iterrows()]) if geo_df is not None else "Datos regionales no disponibles."
            topics_txt = f"Temas: {', '.join(related_topics)}. Consultas: {', '.join(rising_queries)}."
            
            extra_inst = ""
            if is_simulation and "específico" in simulation_reason:
                extra_inst = f"NOTA: El usuario buscó '{keyword}', que es muy específico. Asume el rol de experto y analiza el TEMA general."

            final_prompt = get_trend_synthesis_prompt(keyword, trend_txt + extra_inst, geo_txt, topics_txt, internal_context)
            stream = call_gemini_stream(final_prompt)
            
            status.update(label="¡Análisis 360 Completado!", state="complete", expanded=False)

        # --- DASHBOARD DE RESULTADOS ---
        
        # 1. KPIs
        growth = calculate_growth(trend_df)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Interés Actual", f"{int(trend_df['Interés'].iloc[-1])}/100")
        k2.metric("Tendencia (Crecimiento)", f"{growth:.1f}%", delta_color="normal" if growth > 0 else "inverse")
        k3.metric("Fuente", "IA Estimada" if is_simulation else "Google Live")
        k4.metric("Validación Interna", "Sí" if len(internal_context) > 100 else "No", delta="Repo" if len(internal_context)>100 else None)

        if is_simulation:
            st.info(f"ℹ️ **Modo: {simulation_reason}** Los datos visuales son simulados, pero el análisis estratégico es real.")

        # 2. Gráficos (Pestañas)
        tab_time, tab_geo, tab_rel = st.tabs(["📈 Evolución Temporal", "🗺️ Mapa de Calor", "🔗 Contexto Semántico"])
        
        with tab_time:
            c = alt.Chart(trend_df).mark_area(
                line={'color':'#29B5E8'},
                color=alt.Gradient(gradient='linear', stops=[alt.GradientStop(color='#29B5E8', offset=0), alt.GradientStop(color='white', offset=1)], x1=1, x2=1, y1=1, y2=0)
            ).encode(x=alt.X('Fecha:T'), y=alt.Y('Interés:Q'), tooltip=['Fecha', 'Interés']).properties(height=300)
            st.altair_chart(c, use_container_width=True)

        with tab_geo:
            if geo_df is not None and not geo_df.empty:
                c_geo = alt.Chart(geo_df).mark_bar().encode(
                    x=alt.X('Interés:Q'),
                    y=alt.Y('Región:N', sort='-x'),
                    color=alt.Color('Interés:Q', scale=alt.Scale(scheme='blues')),
                    tooltip=['Región', 'Interés']
                ).properties(height=400)
                st.altair_chart(c_geo, use_container_width=True)
            else:
                st.caption("No hay suficientes datos regionales para este término.")

        with tab_rel:
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                st.markdown("**🔥 Consultas en Aumento**")
                if rising_queries:
                    for q in rising_queries: st.markdown(f"- 📈 {q}")
                else: st.caption("Sin datos.")
            with c_col2:
                st.markdown("**💡 Temas Relacionados**")
                if related_topics:
                    for t in related_topics: st.markdown(f"- 🏷️ {t}")
                else: st.caption("Sin datos.")

        # 3. Output Estratégico
        st.divider()
        st.markdown("### 🧠 Brief Estratégico Atelier")
        if stream: st.write_stream(stream)
        
        if len(internal_context) > 100:
            with st.expander("Ver evidencia del repositorio interno"):
                st.markdown(internal_context)
