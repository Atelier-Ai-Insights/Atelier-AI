import streamlit as st
import pandas as pd
import altair as alt
from pytrends.request import TrendReq
from services.gemini_api import call_gemini_stream, call_gemini_api
from utils import render_process_status
from prompts import get_trend_synthesis_prompt
import random
import json

# --- IMPORTS DE LOGS ---
from services.supabase_db import log_query_event
import constants as c

# =====================================================
# MOTOR DE BÚSQUEDA SEMÁNTICA (INTEGRADO)
# =====================================================

def smart_internal_search(db, keyword):
    """
    1. Expande la keyword usando IA (Sinónimos/Categorías).
    2. Busca en el repositorio fragmentos que coincidan con CUALQUIERA de los términos.
    3. Retorna un contexto denso y relevante.
    """
    # 1. Expansión Semántica
    expand_prompt = f"Para investigar '{keyword}' en una base de datos de investigación de mercados, dame 3 palabras clave adicionales (sinónimos, categorías superiores o temas técnicos relacionados). Solo las palabras separadas por coma, nada más."
    try:
        variants_str = call_gemini_api(expand_prompt)
        variants = [v.strip().lower() for v in variants_str.split(',')]
    except:
        variants = []
    
    search_terms = [keyword.lower()] + variants
    st.caption(f"🕵️ **Rastreador Interno activado:** Buscando huellas de: *{', '.join(search_terms)}*")

    # 2. Barrido del Repositorio
    hits = []
    
    for doc in db:
        doc_name = doc.get('nombre_archivo', 'Documento sin nombre')
        content_chunks = []
        for grupo in doc.get("grupos", []):
            content_chunks.append(str(grupo.get('contenido_texto', '')))
        
        full_text = " ".join(content_chunks).lower()
        
        # Scoring simple
        score = 0
        matched_terms = []
        for term in search_terms:
            if term in full_text:
                score += 1
                matched_terms.append(term)
        
        if score > 0:
            # Snippet
            start_idx = -1
            for term in matched_terms:
                idx = full_text.find(term)
                if idx != -1:
                    start_idx = idx
                    break
            
            snippet_start = max(0, start_idx - 100)
            snippet_end = min(len(full_text), start_idx + 400)
            snippet = full_text[snippet_start:snippet_end] + "..."
            
            hits.append({
                "doc": doc_name,
                "score": score,
                "snippet": snippet,
                "matches": matched_terms
            })

    # 3. Ordenar
    hits.sort(key=lambda x: x['score'], reverse=True)
    top_hits = hits[:7] 
    
    if not top_hits:
        return ""

    context_str = f"--- RESULTADOS DE BÚSQUEDA INTERNA (Términos: {', '.join(search_terms)}) ---\n\n"
    for hit in top_hits:
        context_str += f"📄 **Documento:** {hit['doc']}\n"
        context_str += f"   *Coincidencias:* {', '.join(hit['matches'])}\n"
        context_str += f"   *Fragmento:* \"...{hit['snippet']}...\"\n\n"
        
    return context_str

# =====================================================
# MODO: TREND RADAR 360 (CORREGIDO)
# =====================================================

def calculate_growth(df):
    if df.empty or len(df) < 2: return 0
    first_half = df['Interés'].iloc[:len(df)//2].mean()
    last_half = df['Interés'].iloc[len(df)//2:].mean()
    if first_half == 0: return 100 if last_half > 0 else 0
    return ((last_half - first_half) / first_half) * 100

def google_trends_mode():
    st.subheader("📡 Radar de Tendencias 360°")
    st.markdown("Triangulación inteligente: **Mercado** + **Repositorio Semántico** + **IA**.")

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        keyword = c1.text_input("Término:", placeholder="Ej: Sellos Octagonales")
        market = c2.selectbox("Mercado", ["Colombia", "México", "Global"], index=0)
        timeframe = c3.selectbox("Tiempo", ["today 1-m", "today 12-m", "today 5-y"], format_func=lambda x: "30 Días" if "1-m" in x else "1 Año" if "12-m" in x else "5 Años")

    geo_map = {"Colombia": "CO", "México": "MX", "Global": ""}
    geo_code = geo_map[market]

    if st.button("Escanear Tendencia", type="primary", use_container_width=True):
        if not keyword: st.warning("Ingresa un término."); return

        trend_df, geo_df = None, None
        rising_queries, related_topics = [], []
        internal_context = ""
        is_simulation = False
        simulation_reason = ""
        
        db = st.session_state.get("db_full", [])

        with render_process_status(f"Analizando '{keyword}'...", expanded=True) as status:
            
            # 1. BÚSQUEDA SEMÁNTICA INTERNA
            status.write("🧠 Activando puente semántico con repositorio...")
            if db:
                internal_context = smart_internal_search(db, keyword)
            
            # 2. GOOGLE TRENDS
            status.write("🌍 Consultando Google Trends Live...")
            try:
                pytrends = TrendReq(hl='es', tz=300, timeout=(5, 20))
                pytrends.build_payload([keyword], cat=0, timeframe=timeframe, geo=geo_code)
                
                data = pytrends.interest_over_time()
                if data.empty: raise ValueError("EmptyData")
                
                trend_df = data.reset_index().rename(columns={keyword: 'Interés', 'date': 'Fecha'})
                
                # Geo
                try:
                    geo_data = pytrends.interest_by_region(resolution='REGION', inc_low_vol=True)
                    geo_data = geo_data[geo_data[keyword] > 0].sort_values(keyword, ascending=False).head(10)
                    if not geo_data.empty: geo_df = geo_data.reset_index().rename(columns={keyword: 'Interés', 'geoName': 'Región'})
                except: pass

                # Topics
                try:
                    rel_q = pytrends.related_queries()
                    if rel_q and keyword in rel_q:
                        if rel_q[keyword]['rising'] is not None: rising_queries = rel_q[keyword]['rising'].head(5)['query'].tolist()
                    
                    rel_t = pytrends.related_topics()
                    if rel_t and keyword in rel_t:
                        if rel_t[keyword]['rising'] is not None: related_topics = rel_t[keyword]['rising'].head(5)['topic_title'].tolist()
                except: pass

            except Exception as e:
                is_simulation = True
                simulation_reason = "Término muy específico" if "EmptyData" in str(e) else "Bloqueo API Google"
                
                # Datos Simulados
                dates = pd.date_range(end=pd.Timestamp.now(), periods=52, freq='W')
                values = [min(100, max(0, random.randint(20, 60) + (i * 0.5) + random.randint(-10, 10))) for i in range(52)]
                trend_df = pd.DataFrame({'Fecha': dates, 'Interés': values})
                rising_queries = [f"futuro {keyword}", f"impacto {keyword}", f"novedades {keyword}"]

            # 3. SÍNTESIS
            status.write("💡 Cruzando hallazgos...")
            trend_txt = f"Tendencia {'simulada' if is_simulation else 'real'}. Valor final: {trend_df['Interés'].iloc[-1]}."
            geo_txt = "Datos geo no disponibles." if geo_df is None else str(geo_df.to_dict())
            topics_txt = f"Temas: {', '.join(related_topics)}. Queries: {', '.join(rising_queries)}."
            
            extra = f"NOTA: El usuario buscó '{keyword}'. Google Trends falló ({simulation_reason}). Asume rol experto." if is_simulation else ""

            prompt = get_trend_synthesis_prompt(keyword, trend_txt + extra, geo_txt, topics_txt, internal_context)
            stream = call_gemini_stream(prompt)
            
            status.update(label="¡Análisis Finalizado!", state="complete", expanded=False)

        # --- DASHBOARD ---
        growth = calculate_growth(trend_df)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Interés", f"{int(trend_df['Interés'].iloc[-1])}/100")
        k2.metric("Dinámica", f"{growth:.1f}%", delta_color="normal" if growth>0 else "inverse")
        k3.metric("Fuente", "Simulación IA" if is_simulation else "Google Live")
        k4.metric("Conexión Interna", "Fuerte" if len(internal_context)>500 else "Débil" if len(internal_context)>50 else "Nula", 
                 delta="Hallazgos" if len(internal_context)>50 else "Sin datos")

        if is_simulation: st.warning(f"⚠️ **Modo Estimación:** {simulation_reason}. Análisis basado en IA.")

        t1, t2, t3 = st.tabs(["Temporal", "Geográfico", "Contexto"])
        
        with t1:
            # CAMBIO: Usamos chart_time en lugar de c para evitar conflictos
            chart_time = alt.Chart(trend_df).mark_area(
                line={'color':'#29B5E8'}, 
                color=alt.Gradient(gradient='linear', stops=[alt.GradientStop(color='#29B5E8', offset=0), alt.GradientStop(color='white', offset=1)], x1=1, x2=1, y1=1, y2=0)
            ).encode(x='Fecha:T', y='Interés:Q', tooltip=['Fecha', 'Interés']).properties(height=300)
            
            st.altair_chart(chart_time, use_container_width=True)
        
        with t2:
            if geo_df is not None:
                st.altair_chart(alt.Chart(geo_df).mark_bar().encode(x='Interés:Q', y=alt.Y('Región:N', sort='-x'), color='Interés:Q', tooltip=['Región', 'Interés']).properties(height=400), use_container_width=True)
            else: st.caption("Sin datos regionales.")

        with t3:
            if rising_queries:
                st.write("**🔥 Búsquedas relacionadas:**")
                st.markdown(" ".join([f"`{q}`" for q in rising_queries]))
            
            if len(internal_context) > 50:
                st.divider()
                st.markdown("**🗂️ Evidencia encontrada en el repositorio:**")
                with st.container(height=200):
                    st.markdown(internal_context)

        st.divider()
        st.markdown("### Brief de Estrategia")
        
        if stream:
            st.write_stream(stream)
            # REGISTRO EN SUPABASE (Ahora funcionará porque 'c' es el módulo constants)
            try:
                log_query_event(f"Trend Radar: {keyword}", mode=c.MODE_TREND_ANALYSIS)
            except Exception as e:
                print(f"Error logging: {e}")
