import streamlit as st
import pandas as pd
from services.supabase_db import supabase, supabase_admin_client
from config import PLAN_FEATURES
from supabase import create_client 
import altair as alt 

# =====================================================
# FUNCIÓN DEL DASHBOARD DEL REPOSITORIO (MODIFICADA)
# =====================================================
def show_repository_dashboard(db_full):
    st.subheader("Dashboard de Tendencias del Repositorio")
    st.markdown("Una vista de helicóptero de todo el conocimiento en la base de datos.")

    if not db_full:
        st.warning("No hay datos en el repositorio para analizar.")
        return

    # --- 1. Preparar Datos ---
    try:
        df = pd.DataFrame(db_full)
        # Limpiar datos para los gráficos
        df['marca'] = df['marca'].fillna('Sin Año').astype(str)
        df['filtro'] = df['filtro'].fillna('Sin Marca').astype(str)
        df['cliente'] = df['cliente'].fillna('Sin Cliente').astype(str)
        
    except Exception as e:
        st.error(f"Error al procesar los datos del repositorio: {e}")
        return
            
    # --- 2. Mostrar Gráficos ---
    st.markdown("#### Distribución de Estudios")
    
    # Gráfico de Año (Vertical)
    st.markdown("**Estudios por Año (campo 'marca')**")
    year_counts = df['marca'].value_counts().sort_index()
    st.bar_chart(year_counts)

    st.divider()
    
    # --- ¡INICIO DE MODIFICACIÓN! Se eliminaron las columnas ---
    
    # Gráfico de Cliente (Pie Chart)
    st.markdown("**Estudios por Cliente (campo 'cliente')**")
    
    try:
        cliente_counts_series = df['cliente'].value_counts()
        cliente_counts_df = cliente_counts_series.reset_index()
        cliente_counts_df.columns = ['Cliente', 'Conteo']
        
        if not cliente_counts_df.empty:
            base = alt.Chart(cliente_counts_df).encode(
               theta=alt.Theta("Conteo:Q", stack=True)
            )

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

            chart = pie + text
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No hay datos de clientes para mostrar en el gráfico.")
    
    except Exception as e:
        st.error(f"Se produjo un error al generar el gráfico de pastel: {e}")

    st.divider() # Separador añadido

    # Gráfico de Marca (Tabla)
    st.markdown("**Estudios por Marca (campo 'filtro')**")
    filtro_counts = df['filtro'].value_counts().reset_index()
    filtro_counts.columns = ['Marca', 'Conteo']
    st.dataframe(filtro_counts.set_index('Marca'), use_container_width=True)
    
    # --- ¡FIN DE MODIFICACIÓN! ---


# =====================================================
# PANEL DE ADMINISTRACIÓN (MODIFICADO)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("Error: La 'SUPABASE_SERVICE_KEY' no está configurada...")
        return

    tab_stats, tab_repo = st.tabs(["Estadísticas y Costos", "Dashboard del Repositorio"])

    with tab_stats:
        st.subheader("Estadísticas de Uso y Consumo (Tokens)", divider="grey")
        with st.spinner("Cargando estadísticas..."):
            try:
                stats_response = supabase.table("queries").select("user_name, mode, timestamp, query, total_tokens").execute()
                
                if stats_response.data:
                    df_stats = pd.DataFrame(stats_response.data)
                    df_stats['timestamp'] = pd.to_datetime(df_stats['timestamp']).dt.tz_localize(None)
                    df_stats['date'] = df_stats['timestamp'].dt.date
                    
                    if 'total_tokens' in df_stats.columns:
                        df_stats['total_tokens'] = df_stats['total_tokens'].fillna(0).astype(int)
                    else:
                        df_stats['total_tokens'] = 0 

                    # --- Métricas Generales (Esto se mantiene en 3 columnas) ---
                    total_queries = len(df_stats)
                    total_tokens_consumed = df_stats['total_tokens'].sum()
                    
                    ESTIMATED_COST_PER_MILLION_TOKENS = 0.30 
                    estimated_cost = (total_tokens_consumed / 1_000_000) * ESTIMATED_COST_PER_MILLION_TOKENS 

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total Consultas (Global)", total_queries)
                    m2.metric("Total Tokens Procesados", f"{total_tokens_consumed:,.0f}")
                    m3.metric("Costo Estimado (aprox.)", f"${estimated_cost:.4f} USD")
                    st.divider()
                    
                    # --- ¡INICIO DE MODIFICACIÓN! Se eliminaron las columnas ---

                    st.write("**Top Usuarios por Consumo (Tokens)**")
                    user_tokens = df_stats.groupby('user_name')['total_tokens'].sum().reset_index(name='Tokens Totales').sort_values(by="Tokens Totales", ascending=False)
                    st.dataframe(user_tokens, use_container_width=True, hide_index=True)
                    st.bar_chart(user_tokens.set_index('user_name'))

                    st.divider() # Separador añadido

                    st.write("**Consumo por Modo de Uso (Tokens)**")
                    mode_tokens = df_stats.groupby('mode')['total_tokens'].sum().reset_index(name='Tokens Totales').sort_values(by="Tokens Totales", ascending=False)
                    st.dataframe(mode_tokens, use_container_width=True, hide_index=True)
                    
                    base = alt.Chart(mode_tokens).encode(
                        theta=alt.Theta("Tokens Totales:Q", stack=True)
                    ).properties(title="Distribución de Tokens por Modo")
                    
                    pie = base.mark_arc(outerRadius=120).encode(
                        color=alt.Color("mode:N", title="Modo"),
                        order=alt.Order("Tokens Totales", sort="descending"),
                        tooltip=["mode", "Tokens Totales"]
                    )
                    st.altair_chart(pie, use_container_width=True)
                        
                    st.divider() # Separador añadido
                    
                    st.write("**Actividad Reciente (Últimas 50 consultas)**")
                    df_recent = df_stats[['timestamp', 'user_name', 'mode', 'total_tokens', 'query']].sort_values(by="timestamp", ascending=False).head(50)
                    df_recent['timestamp'] = df_recent['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
                    st.dataframe(df_recent, use_container_width=True, hide_index=True)
                    
                    # --- ¡FIN DE MODIFICACIÓN! ---
                else: 
                    st.info("Aún no hay datos de uso.")
            except Exception as e: 
                st.error(f"Error cargando estadísticas: {e}")

        # --- (Gestión de Clientes y Usuarios no cambia) ---
        st.subheader("Gestión de Clientes (Invitaciones)", divider="grey")
        try:
            clients_response = supabase_admin_client.table("clients").select("client_name, plan, invite_code, created_at").order("created_at", desc=True).execute()
            if clients_response.data: 
                st.write("**Clientes Actuales**")
                df_clients = pd.DataFrame(clients_response.data)
                df_clients['created_at'] = pd.to_datetime(df_clients['created_at']).dt.strftime('%Y-%m-%d')
                st.dataframe(df_clients, use_container_width=True, hide_index=True)
            else: 
                st.info("No hay clientes.")
        except Exception as e: 
            st.error(f"Error cargando clientes: {e}")

        with st.expander("➕ Crear Nuevo Cliente y Código"):
            with st.form("new_client_form"):
                new_client_name = st.text_input("Nombre")
                new_plan = st.selectbox("Plan", options=list(PLAN_FEATURES.keys()), index=0)
                new_invite_code = st.text_input("Código Invitación")
                submitted = st.form_submit_button("Crear Cliente")
                
                if submitted:
                    if not new_client_name or not new_plan or not new_invite_code: 
                        st.warning("Completa campos.")
                    else:
                        try: 
                            supabase_admin_client.table("clients").insert({"client_name": new_client_name, "plan": new_plan, "invite_code": new_invite_code}).execute()
                            st.success(f"Cliente '{new_client_name}' creado. Código: {new_invite_code}")
                        except Exception as e: 
                            st.error(f"Error al crear: {e}")

        st.subheader("Gestión de Usuarios", divider="grey")
        
        try:
            users_response = supabase_admin_client.table("users").select("id, email, created_at, rol, client_id, clients(client_name, plan)").order("created_at", desc=True).execute()

            if users_response.data:
                st.write("**Usuarios Registrados** (Puedes editar Rol)")
                user_list = []
                for user in users_response.data:
                    client_info = user.get('clients')
                    client_name = "N/A"; client_plan = "N/A"
                    if isinstance(client_info, dict):
                        client_name = client_info.get('client_name', "N/A")
                        client_plan = client_info.get('plan', "N/A")
                    user_list.append({
                        'id': user.get('id'), 'email': user.get('email'), 'creado_el': user.get('created_at'),
                        'rol': user.get('rol', 'user'), 'cliente': client_name, 'plan': client_plan
                    })
                    
                original_df = pd.DataFrame(user_list)
                if 'original_users_df' not in st.session_state: 
                    st.session_state.original_users_df = original_df.copy()
                    
                display_df = original_df.copy()
                display_df['creado_el'] = pd.to_datetime(display_df['creado_el']).dt.strftime('%Y-%m-%d %H:%M')
                
                edited_df = st.data_editor( 
                    display_df, 
                    key="user_editor", 
                    column_config={
                        "id": None, 
                        "rol": st.column_config.SelectboxColumn("Rol", options=["user", "admin"], required=True), 
                        "email": st.column_config.TextColumn("Email", disabled=True), 
                        "creado_el": st.column_config.TextColumn("Creado", disabled=True), 
                        "cliente": st.column_config.TextColumn("Cliente", disabled=True), 
                        "plan": st.column_config.TextColumn("Plan", disabled=True)
                    }, 
                    use_container_width=True, 
                    hide_index=True, 
                    num_rows="fixed"
                )
                
                if st.button("Guardar Cambios Usuarios", use_container_width=True):
                    updates_to_make = []
                    original_users = st.session_state.original_users_df
                    edited_df_indexed = edited_df.set_index(original_df.index)
                    edited_df_with_ids = original_df[['id']].join(edited_df_indexed)
                    
                    for index, original_row in original_users.iterrows():
                        edited_rows_match = edited_df_with_ids[edited_df_with_ids['id'] == original_row['id']]
                        if not edited_rows_match.empty:
                            edited_row = edited_rows_match.iloc[0]
                            if original_row['rol'] != edited_row['rol']: 
                                updates_to_make.append({"id": original_row['id'], "email": original_row['email'], "new_rol": edited_row['rol']})
                        else: 
                            print(f"Warn: Row ID {original_row['id']} not in edited df.")
                            
                    if updates_to_make:
                        success_count, error_count, errors = 0, 0, []
                        with st.spinner(f"Guardando {len(updates_to_make)} cambio(s)..."):
                            for update in updates_to_make:
                                try: 
                                    supabase_admin_client.table("users").update({"rol": update["new_rol"]}).eq("id", update["id"]).execute()
                                    success_count += 1
                                except Exception as e: 
                                    errors.append(f"Error {update['email']} (ID: {update['id']}): {e}")
                                    error_count += 1
                                    
                        if success_count > 0: st.success(f"{success_count} actualizado(s).")
                        if error_count > 0: 
                            st.error(f"{error_count} error(es):"); [st.error(f"- {err}") for err in errors]
                            
                        del st.session_state.original_users_df
                        st.rerun()
                    else:
                        st.info("No se detectaron cambios.")
            else:
                st.info("No hay usuarios registrados.")
        except Exception as e:
            st.error(f"Error en la gestión de usuarios: {e}")

    # --- PESTAÑA 2: Dashboard del Repositorio ---
    with tab_repo:
        show_repository_dashboard(db_full)
