import streamlit as st
import pandas as pd
from services.supabase_db import supabase, supabase_admin_client
import altair as alt 

# =====================================================
# FUNCIÓN DEL DASHBOARD DEL REPOSITORIO
# =====================================================
def show_repository_dashboard(db_full):
    st.subheader("Dashboard de Tendencias del Repositorio")
    st.markdown("Una vista de helicóptero de todo el conocimiento en la base de datos.")

    if not db_full:
        st.warning("No hay datos en el repositorio para analizar.")
        return

    try:
        df = pd.DataFrame(db_full)
        df['marca'] = df['marca'].fillna('Sin Año').astype(str)
        df['filtro'] = df['filtro'].fillna('Sin Marca').astype(str)
        df['cliente'] = df['cliente'].fillna('Sin Cliente').astype(str)
        
    except Exception as e:
        st.error(f"Error al procesar los datos del repositorio: {e}")
        return
            
    st.markdown("#### Distribución de Estudios")
    year_counts = df['marca'].value_counts().sort_index()
    st.bar_chart(year_counts)

    st.divider()
    
    st.markdown("**Estudios por Cliente**")
    try:
        cliente_counts_series = df['cliente'].value_counts()
        cliente_counts_df = cliente_counts_series.reset_index()
        cliente_counts_df.columns = ['Cliente', 'Conteo']
        
        if not cliente_counts_df.empty:
            base = alt.Chart(cliente_counts_df).encode(theta=alt.Theta("Conteo:Q", stack=True))
            pie = base.mark_arc(outerRadius=120).encode(
                color=alt.Color("Cliente:N"),
                order=alt.Order("Conteo:Q", sort="descending"),
                tooltip=["Cliente", "Conteo"]
            )
            text = base.mark_text(radius=140).encode(
                text=alt.Text("Conteo:Q", format=".1%"),
                order=alt.Order("Conteo:Q", sort="descending"),
                color=alt.value("black") 
            )
            st.altair_chart(pie + text, width='stretch')
        else:
            st.info("No hay datos de clientes.")
    except Exception as e: st.error(f"Error gráfico pastel: {e}")

    st.divider()

    st.markdown("**Estudios por Marca**")
    filtro_counts = df['filtro'].value_counts().reset_index()
    filtro_counts.columns = ['Marca', 'Conteo']
    st.dataframe(filtro_counts.set_index('Marca'), width='stretch')


# =====================================================
# PANEL DE ADMINISTRACIÓN (ACTUALIZADO: TABLAS VERTICALES + HISTORIAL)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("⚠️ Error de Configuración: No se encontró 'SUPABASE_SERVICE_KEY'.")
        return

    if "invite_counter" not in st.session_state:
        st.session_state.invite_counter = 0

    tab_stats, tab_users, tab_repo = st.tabs(["Estadísticas & Costos", "Gestión Usuarios", "Repositorio"])

    # --- PESTAÑA 1: ESTADÍSTICAS FINANCIERAS ---
    with tab_stats:
        st.subheader("Estadísticas de Uso y Rentabilidad", divider="grey")
        
        with st.spinner("Procesando datos de consumo..."):
            try:
                # 1. Cargar Datos
                stats_response = supabase.table("queries").select("user_name, mode, query, timestamp, total_tokens").execute()
                users_resp = supabase_admin_client.table("users").select("email, client_id").execute()
                clients_resp = supabase_admin_client.table("clients").select("id, client_name").execute()

                if stats_response.data:
                    # Dataframes base
                    df_queries = pd.DataFrame(stats_response.data)
                    df_users = pd.DataFrame(users_resp.data) if users_resp.data else pd.DataFrame(columns=['email', 'client_id'])
                    df_clients = pd.DataFrame(clients_resp.data) if clients_resp.data else pd.DataFrame(columns=['id', 'client_name'])

                    # Limpieza y Conversión
                    df_queries['timestamp'] = pd.to_datetime(df_queries['timestamp']).dt.tz_localize(None)
                    df_queries['total_tokens'] = df_queries['total_tokens'].fillna(0).astype(int)

                    # Cruce de Datos (Joins)
                    df_merged = pd.merge(df_queries, df_users, left_on='user_name', right_on='email', how='left')
                    df_final = pd.merge(df_merged, df_clients, left_on='client_id', right_on='id', how='left')
                    df_final['client_name'] = df_final['client_name'].fillna('Sin Empresa / Admin')

                    # Constante de Costo
                    COST_PER_1M = 0.30 

                    # --- KPI GLOBALES ---
                    total_queries = len(df_queries)
                    total_tokens = df_queries['total_tokens'].sum()
                    est_cost_global = (total_tokens / 1_000_000) * COST_PER_1M 

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total Consultas", total_queries)
                    m2.metric("Tokens Totales", f"{total_tokens:,.0f}")
                    m3.metric("Costo Global ($USD)", f"${est_cost_global:.4f}")
                    
                    st.divider()

                    # --- 1. ANÁLISIS POR EMPRESA (VERTICAL) ---
                    st.markdown("### 🏢 Consumo por Empresa")
                    
                    client_stats = df_final.groupby('client_name').agg(
                        Consultas=('id', 'count'),
                        Tokens=('total_tokens', 'sum')
                    ).reset_index()
                    
                    client_stats['Costo ($)'] = (client_stats['Tokens'] / 1_000_000) * COST_PER_1M
                    client_stats = client_stats.sort_values('Tokens', ascending=False)

                    # Gráfico (Ancho completo)
                    st.bar_chart(client_stats.set_index('client_name')['Tokens'], color="#0068c9")
                    
                    # Tabla (Ancho completo, debajo)
                    st.dataframe(
                        client_stats.style.format({"Costo ($)": "${:.4f}"}),
                        column_config={
                            "client_name": "Empresa",
                            "Tokens": st.column_config.NumberColumn("Tokens Totales"),
                        },
                        hide_index=True, 
                        use_container_width=True
                    )

                    st.divider()

                    # --- 2. ANÁLISIS POR USUARIO (VERTICAL) ---
                    st.markdown("### 👤 Consumo por Usuario")
                    
                    user_stats = df_final.groupby(['user_name', 'client_name']).agg(
                        Consultas=('id', 'count'),
                        Tokens=('total_tokens', 'sum')
                    ).reset_index()
                    
                    user_stats['Costo ($)'] = (user_stats['Tokens'] / 1_000_000) * COST_PER_1M
                    user_stats = user_stats.sort_values('Tokens', ascending=False)

                    st.dataframe(
                        user_stats.style.format({"Costo ($)": "${:.4f}"}),
                        column_config={
                            "user_name": "Usuario",
                            "client_name": "Empresa",
                            "Tokens": st.column_config.NumberColumn("Tokens"),
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                    st.divider()

                    # --- 3. HISTORIAL DE BÚSQUEDAS (NUEVA TABLA) ---
                    st.markdown("### 🔎 Historial de Búsquedas Detallado")
                    st.caption("Registro auditor de cada consulta realizada, incluyendo el prompt del usuario y el costo individual.")

                    # Preparamos la tabla de auditoría
                    audit_df = df_final[['timestamp', 'user_name', 'client_name', 'mode', 'query', 'total_tokens']].copy()
                    audit_df['Costo ($)'] = (audit_df['total_tokens'] / 1_000_000) * COST_PER_1M
                    audit_df = audit_df.sort_values('timestamp', ascending=False)

                    st.dataframe(
                        audit_df.style.format({"Costo ($)": "${:.5f}"}),
                        column_config={
                            "timestamp": st.column_config.DatetimeColumn("Fecha y Hora", format="D MMM YYYY, HH:mm"),
                            "user_name": "Usuario",
                            "client_name": "Empresa",
                            "mode": "Herramienta Usada",
                            "query": st.column_config.TextColumn("Consulta (Prompt)", width="large"),
                            "total_tokens": st.column_config.NumberColumn("Tokens"),
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=500 # Altura fija para scrollear si son muchas
                    )

                else: st.info("Aún no hay datos de uso registrados.")
            except Exception as e: st.error(f"Error calculando estadísticas: {e}")

    # --- PESTAÑA 2: GESTIÓN DE USUARIOS ---
    with tab_users:
        st.subheader("📩 Invitar Usuario Nuevo", divider="blue")
        st.info("Usa esto para enviar un correo de invitación oficial.")
        
        if "admin_invite_success" in st.session_state:
            st.success(st.session_state.admin_invite_success)
            del st.session_state.admin_invite_success

        try:
            clients_data = supabase_admin_client.table("clients").select("id, client_name").execute().data
            client_options = {c['client_name']: c['id'] for c in clients_data} if clients_data else {}
        except: client_options = {}

        with st.form("invite_user_form"):
            col_inv_1, col_inv_2 = st.columns(2)
            new_email = col_inv_1.text_input("Correo electrónico", key=f"admin_email_input_{st.session_state.invite_counter}")
            target_client_name = col_inv_2.selectbox("Asignar a Empresa", list(client_options.keys()))
            
            if st.form_submit_button("Enviar Invitación", type="primary"):
                if new_email and target_client_name:
                    try:
                        invite_res = supabase_admin_client.auth.admin.invite_user_by_email(
                            new_email,
                            options={
                                "data": { "client_id": client_options[target_client_name] },
                                "redirect_to": "https://atelier-ai.streamlit.app"
                            }
                        )
                        st.session_state["admin_invite_success"] = f"✅ Invitación enviada a **{new_email}**."
                        st.session_state.invite_counter += 1 
                        st.rerun()
                    except Exception as e:
                        if "already created" in str(e): st.warning("El usuario ya existe.")
                        else: st.error(f"Error: {e}")
                else: st.warning("Faltan datos.")

        st.divider()
        with st.expander("🏢 Gestión de Empresas y Códigos"):
            try:
                clients_resp = supabase_admin_client.table("clients").select("*").order("created_at", desc=True).execute()
                if clients_resp.data: st.dataframe(pd.DataFrame(clients_resp.data)[['client_name', 'invite_code', 'plan']], width='stretch')
                
                st.write("**Crear Empresa**")
                c1, c2, c3, c4 = st.columns([2,2,2,1])
                n_name = c1.text_input("Nombre")
                n_plan = c2.selectbox("Plan", ["Explorer", "Strategist", "Enterprise"])
                n_code = c3.text_input("Código")
                if c4.button("Crear"):
                    supabase_admin_client.table("clients").insert({"client_name": n_name, "plan": n_plan, "invite_code": n_code}).execute(); st.rerun()
            except: pass

        st.divider()
        st.subheader("👥 Usuarios Registrados")
        try:
            users_resp = supabase_admin_client.table("users").select("id, email, created_at, rol, client_id, clients(client_name)").order("created_at", desc=True).execute()
            if users_resp.data:
                user_list = []
                for user in users_resp.data:
                    c_info = user.get('clients')
                    user_list.append({
                        'id': user.get('id'), 'email': user.get('email'), 'rol': user.get('rol', 'user'),
                        'empresa': c_info.get('client_name', "⛔ SIN ASIGNAR") if c_info else "⛔ SIN ASIGNAR",
                        'client_id': user.get('client_id'), 
                        'creado': pd.to_datetime(user.get('created_at')).strftime('%Y-%m-%d')
                    })
                
                edited_df = st.data_editor(pd.DataFrame(user_list), column_config={"id":None,"client_id":None,"email":st.column_config.TextColumn(disabled=True),"empresa":st.column_config.TextColumn(disabled=True),"rol":st.column_config.SelectboxColumn(options=["user","admin"],required=True)}, hide_index=True, width='stretch')
                
                if st.button("Guardar Cambios de Rol"):
                    for i, row in edited_df.iterrows():
                        try: supabase_admin_client.table("users").update({"rol": row['rol']}).eq("id", row['id']).execute()
                        except: pass
                    st.success("Roles actualizados."); st.rerun()
        except Exception as e: st.error(f"Error usuarios: {e}")

    with tab_repo:
        show_repository_dashboard(db_full)
