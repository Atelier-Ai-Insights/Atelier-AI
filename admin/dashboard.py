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
# PANEL DE ADMINISTRACIÓN (CON COSTOS POR CLIENTE)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("⚠️ Error de Configuración: No se encontró 'SUPABASE_SERVICE_KEY'.")
        return

    # Inicializar contador para limpiar formulario
    if "invite_counter" not in st.session_state:
        st.session_state.invite_counter = 0

    tab_stats, tab_users, tab_repo = st.tabs(["Estadísticas & Costos", "Gestión Usuarios", "Repositorio"])

    # --- PESTAÑA 1: ESTADÍSTICAS FINANCIERAS ---
    with tab_stats:
        st.subheader("Estadísticas de Uso y Rentabilidad", divider="grey")
        
        with st.spinner("Calculando costos por cliente..."):
            try:
                # 1. Cargar Queries (Consumo)
                stats_response = supabase.table("queries").select("user_name, mode, timestamp, total_tokens").execute()
                
                # 2. Cargar Usuarios y Clientes (Para cruzar datos)
                users_resp = supabase_admin_client.table("users").select("email, client_id").execute()
                clients_resp = supabase_admin_client.table("clients").select("id, client_name").execute()

                if stats_response.data:
                    # Dataframes base
                    df_queries = pd.DataFrame(stats_response.data)
                    df_users = pd.DataFrame(users_resp.data) if users_resp.data else pd.DataFrame(columns=['email', 'client_id'])
                    df_clients = pd.DataFrame(clients_resp.data) if clients_resp.data else pd.DataFrame(columns=['id', 'client_name'])

                    # Limpieza
                    df_queries['timestamp'] = pd.to_datetime(df_queries['timestamp']).dt.tz_localize(None)
                    df_queries['total_tokens'] = df_queries['total_tokens'].fillna(0).astype(int)

                    # --- CRUCE DE DATOS (JOIN) ---
                    # Unimos Queries con Users por Email
                    df_merged = pd.merge(df_queries, df_users, left_on='user_name', right_on='email', how='left')
                    
                    # Unimos el resultado con Clients por ID
                    df_final = pd.merge(df_merged, df_clients, left_on='client_id', right_on='id', how='left')
                    
                    # Llenar vacíos (Usuarios borrados o admins sin cliente)
                    df_final['client_name'] = df_final['client_name'].fillna('Sin Empresa / Admin')

                    # --- KPI GLOBALES ---
                    total_queries = len(df_queries)
                    total_tokens = df_queries['total_tokens'].sum()
                    # Costo estimado: $0.30 USD por 1M tokens (Input+Output promedio Gemini Flash)
                    COST_PER_1M = 0.30 
                    est_cost_global = (total_tokens / 1_000_000) * COST_PER_1M 

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total Consultas", total_queries)
                    m2.metric("Tokens Totales", f"{total_tokens:,.0f}")
                    m3.metric("Costo Global ($USD)", f"${est_cost_global:.4f}")
                    
                    st.divider()

                    # --- ANÁLISIS POR CLIENTE (EMPRESA) ---
                    st.markdown("### 🏢 Consumo por Empresa (Cliente)")
                    
                    # Agrupar
                    client_stats = df_final.groupby('client_name').agg(
                        Consultas=('id', 'count'),
                        Tokens=('total_tokens', 'sum')
                    ).reset_index()
                    
                    # Calcular Costo
                    client_stats['Costo Estimado ($)'] = (client_stats['Tokens'] / 1_000_000) * COST_PER_1M
                    client_stats['Costo Estimado ($)'] = client_stats['Costo Estimado ($)'].apply(lambda x: f"${x:.4f}")
                    
                    # Ordenar
                    client_stats = client_stats.sort_values('Tokens', ascending=False)

                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.bar_chart(client_stats.set_index('client_name')['Tokens'], color="#0068c9")
                    with c2:
                        st.dataframe(
                            client_stats, 
                            column_config={
                                "client_name": "Empresa",
                                "Tokens": st.column_config.NumberColumn("Tokens", format="%d"),
                            },
                            hide_index=True, 
                            use_container_width=True
                        )

                    st.divider()

                    # --- ANÁLISIS POR USUARIO ---
                    st.markdown("### 👤 Consumo por Usuario")
                    
                    user_stats = df_final.groupby(['user_name', 'client_name']).agg(
                        Consultas=('id', 'count'),
                        Tokens=('total_tokens', 'sum')
                    ).reset_index()
                    
                    user_stats['Costo Estimado ($)'] = (user_stats['Tokens'] / 1_000_000) * COST_PER_1M
                    user_stats['Costo Estimado ($)'] = user_stats['Costo Estimado ($)'].apply(lambda x: f"${x:.4f}")
                    user_stats = user_stats.sort_values('Tokens', ascending=False).head(20) # Top 20

                    st.dataframe(
                        user_stats,
                        column_config={
                            "user_name": "Usuario",
                            "client_name": "Empresa",
                            "Tokens": st.column_config.NumberColumn("Tokens", format="%d"),
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                else: st.info("Aún no hay datos de uso registrados.")
            except Exception as e: st.error(f"Error calculando estadísticas: {e}")

    # --- PESTAÑA 2: GESTIÓN DE USUARIOS E INVITACIONES ---
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
            
            new_email = col_inv_1.text_input(
                "Correo electrónico del usuario", 
                key=f"admin_email_input_{st.session_state.invite_counter}"
            )
            
            target_client_name = col_inv_2.selectbox("Asignar a Empresa (Cliente)", list(client_options.keys()))
            
            btn_invite = st.form_submit_button("Enviar Invitación", type="primary")
            
            if btn_invite:
                if new_email and target_client_name:
                    target_client_id = client_options[target_client_name]
                    try:
                        invite_res = supabase_admin_client.auth.admin.invite_user_by_email(
                            new_email,
                            options={
                                "data": { "client_id": target_client_id },
                                "redirect_to": "https://atelier-ai.streamlit.app"
                            }
                        )
                        st.session_state["admin_invite_success"] = f"✅ Invitación enviada a **{new_email}** para **{target_client_name}**."
                        st.session_state.invite_counter += 1 
                        st.rerun()
                    except Exception as e:
                        if "already created" in str(e):
                            st.warning("El usuario ya existe. Intenta editar su rol abajo.")
                        else:
                            st.error(f"Error al invitar: {e}")
                else:
                    st.warning("Faltan datos.")

        st.divider()
        with st.expander("🏢 Gestión de Empresas y Códigos", expanded=False):
            try:
                clients_resp = supabase_admin_client.table("clients").select("*").order("created_at", desc=True).execute()
                if clients_resp.data: 
                    st.dataframe(pd.DataFrame(clients_resp.data)[['client_name', 'invite_code', 'plan']], width='stretch')
                
                st.write("**Crear Nueva Empresa**")
                c1, c2, c3, c4 = st.columns([2,2,2,1])
                n_name = c1.text_input("Nombre Empresa")
                n_plan = c2.selectbox("Plan", ["Explorer", "Strategist", "Enterprise"])
                n_code = c3.text_input("Código Invitación")
                if c4.button("Crear"):
                    supabase_admin_client.table("clients").insert({"client_name": n_name, "plan": n_plan, "invite_code": n_code}).execute()
                    st.rerun()
            except Exception as e: st.error(f"Error clientes: {e}")

        st.divider()
        st.subheader("👥 Usuarios Registrados")
        try:
            users_resp = supabase_admin_client.table("users").select("id, email, created_at, rol, client_id, clients(client_name)").order("created_at", desc=True).execute()

            if users_resp.data:
                user_list = []
                for user in users_resp.data:
                    client_info = user.get('clients')
                    client_name = client_info.get('client_name', "⛔ SIN ASIGNAR") if client_info else "⛔ SIN ASIGNAR"
                        
                    user_list.append({
                        'id': user.get('id'), 
                        'email': user.get('email'), 
                        'rol': user.get('rol', 'user'), 
                        'empresa': client_name,
                        'client_id': user.get('client_id'), 
                        'creado': pd.to_datetime(user.get('created_at')).strftime('%Y-%m-%d')
                    })
                    
                df_users = pd.DataFrame(user_list)
                
                edited_df = st.data_editor(
                    df_users,
                    column_config={
                        "id": None, "client_id": None,
                        "rol": st.column_config.SelectboxColumn("Rol", options=["user", "admin"], required=True),
                        "email": st.column_config.TextColumn("Email", disabled=True),
                        "empresa": st.column_config.TextColumn("Empresa", disabled=True)
                    },
                    hide_index=True,
                    key="user_editor",
                    width='stretch'
                )
                
                if st.button("Guardar Cambios de Rol"):
                    for index, row in edited_df.iterrows():
                        try:
                            supabase_admin_client.table("users").update({"rol": row['rol']}).eq("id", row['id']).execute()
                        except: pass
                    st.success("Roles actualizados.")
                    st.rerun()
            else:
                st.info("No hay usuarios.")
        except Exception as e:
            st.error(f"Error cargando usuarios: {e}")

    with tab_repo:
        show_repository_dashboard(db_full)
