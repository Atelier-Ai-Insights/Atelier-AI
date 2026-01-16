import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt

# Importación segura
try:
    from services.supabase_db import supabase, supabase_admin_client
except ImportError:
    st.error("Error crítico: No se pudieron cargar los servicios de base de datos.")
    st.stop()

# =====================================================
# PANEL DE ADMINISTRACIÓN (BLINDADO)
# =====================================================
def show_admin_dashboard(db_full): 
    if not supabase_admin_client:
        st.error("⚠️ Error: Falta la 'SUPABASE_SERVICE_KEY' en la configuración (.env o secrets).")
        return

    st.title("Panel de Control")
    
    # Solo 2 pestañas, como pediste
    tab_stats, tab_users = st.tabs(["📊 Reporte de Consumo", "👥 Gestión de Usuarios"])

    # --- PESTAÑA 1: ESTADÍSTICAS (La tabla importante) ---
    with tab_stats:
        st.subheader("Auditoría de Búsquedas y Costos")
        
        try:
            with st.spinner("Cargando registro de consultas..."):
                # 1. Cargar Datos Crudos
                queries_res = supabase.table("queries").select("user_name, mode, query, timestamp, total_tokens").execute()
                users_res = supabase_admin_client.table("users").select("email, client_id").execute()
                clients_res = supabase_admin_client.table("clients").select("id, client_name").execute()

                if queries_res.data:
                    # --- CREACIÓN SEGURA DE DATAFRAMES ---
                    # Esto evita el error de pantalla blanca si alguna tabla viene vacía
                    
                    # A. Queries
                    df_q = pd.DataFrame(queries_res.data)
                    
                    # B. Usuarios (Si está vacío, definimos columnas para evitar error en merge)
                    if users_res.data:
                        df_u = pd.DataFrame(users_res.data)
                    else:
                        df_u = pd.DataFrame(columns=['email', 'client_id'])

                    # C. Clientes (Si está vacío, definimos columnas)
                    if clients_res.data:
                        df_c = pd.DataFrame(clients_res.data)
                    else:
                        df_c = pd.DataFrame(columns=['id', 'client_name'])

                    # --- LIMPIEZA DE DATOS ---
                    df_q['total_tokens'] = df_q['total_tokens'].fillna(0).astype(int)
                    # Manejo seguro de fechas
                    df_q['timestamp'] = pd.to_datetime(df_q['timestamp'])
                    
                    # --- CRUCE DE DATOS (JOINS) ---
                    # 1. Unir Queries con Usuarios (usando email)
                    df_merged = pd.merge(df_q, df_u, left_on='user_name', right_on='email', how='left')
                    
                    # 2. Unir con Clientes (usando client_id)
                    # Aseguramos que los IDs sean del mismo tipo para el merge
                    if not df_merged.empty and 'client_id' in df_merged.columns:
                        df_final = pd.merge(df_merged, df_c, left_on='client_id', right_on='id', how='left')
                    else:
                        df_final = df_merged
                        df_final['client_name'] = 'Desconocido'

                    # Rellenar nulos visuales
                    if 'client_name' in df_final.columns:
                        df_final['client_name'] = df_final['client_name'].fillna('⚠️ Sin Asignar')
                    else:
                        df_final['client_name'] = '⚠️ Sin Asignar'

                    # --- CÁLCULO DE COSTOS ---
                    COST_PER_1M = 0.30
                    df_final['Costo ($)'] = (df_final['total_tokens'] / 1_000_000) * COST_PER_1M

                    # --- MÉTRICAS ---
                    total_tokens = df_final['total_tokens'].sum()
                    total_cost = df_final['Costo ($)'].sum()
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Consultas", len(df_final))
                    c2.metric("Tokens Consumidos", f"{total_tokens:,.0f}")
                    c3.metric("Costo Estimado ($)", f"${total_cost:.4f}")

                    st.divider()

                    # --- TABLA PRINCIPAL ---
                    st.markdown("### 📋 Detalle de Consultas")
                    
                    # Seleccionamos y ordenamos columnas solo si existen
                    cols_to_show = ['timestamp', 'client_name', 'user_name', 'mode', 'query', 'total_tokens', 'Costo ($)']
                    # Filtramos columnas que realmente existan en el DF final
                    cols_final = [c for c in cols_to_show if c in df_final.columns]
                    
                    df_display = df_final[cols_final].sort_values('timestamp', ascending=False)
                    
                    st.dataframe(
                        df_display.style.format({
                            "Costo ($)": "${:.5f}", 
                            "total_tokens": "{:,.0f}",
                            "timestamp": lambda t: t.strftime("%d %b %Y, %H:%M") if pd.notnull(t) else ""
                        }),
                        column_config={
                            "timestamp": "Fecha",
                            "client_name": "Empresa",
                            "user_name": "Usuario",
                            "mode": "Herramienta",
                            "query": st.column_config.TextColumn("Prompt / Consulta", width="large"),
                            "total_tokens": "Tokens",
                        },
                        use_container_width=True,
                        height=600
                    )
                else:
                    st.info("No hay registros de búsquedas todavía.")

        except Exception as e:
            st.error(f"Error procesando estadísticas: {e}")
            # Imprimimos error en consola para debug si es necesario
            print(f"DEBUG ERROR STATS: {e}")


    # --- PESTAÑA 2: USUARIOS (Invitación con Cliente) ---
    with tab_users:
        st.subheader("Gestión de Accesos")

        # 1. Obtener lista de clientes para el dropdown
        client_options = {}
        try:
            c_data = supabase_admin_client.table("clients").select("id, client_name").execute().data
            if c_data:
                client_options = {c['client_name']: c['id'] for c in c_data}
        except: pass

        # 2. Formulario de Invitación
        with st.container(border=True):
            st.markdown("##### ✉️ Invitar Nuevo Usuario")
            with st.form("invite_form"):
                col1, col2 = st.columns(2)
                email = col1.text_input("Correo electrónico")
                
                empresa_selec = col2.selectbox(
                    "Asignar a Empresa", 
                    options=list(client_options.keys()) if client_options else ["Sin Empresas disponibles"]
                )

                if st.form_submit_button("Enviar Invitación", type="primary"):
                    if not email:
                        st.warning("Escribe un correo.")
                    elif not client_options:
                         st.warning("No hay empresas configuradas.")
                    else:
                        target_id = client_options[empresa_selec]
                        try:
                            supabase_admin_client.auth.admin.invite_user_by_email(
                                email, 
                                options={
                                    "data": { "client_id": target_id },
                                    "redirect_to": "https://atelier-ai.streamlit.app"
                                }
                            )
                            st.success(f"✅ Invitación enviada a {email} para empresa '{empresa_selec}'")
                        except Exception as e:
                            if "already created" in str(e): st.warning("El usuario ya existe.")
                            else: st.error(f"Error: {e}")

        st.divider()

        # 3. Lista de Usuarios (Solo Lectura)
        st.markdown("##### 👥 Directorio Actual")
        try:
            users = supabase_admin_client.table("users").select("email, created_at, rol, client_id, clients(client_name)").order("created_at", desc=True).execute()
            if users.data:
                flat_users = []
                for u in users.data:
                    c_info = u.get('clients')
                    # Manejo seguro si clients es null
                    empresa_nombre = c_info['client_name'] if c_info else "⛔ Sin Asignar"
                    
                    flat_users.append({
                        "Registrado": pd.to_datetime(u['created_at']).strftime('%Y-%m-%d'),
                        "Email": u['email'],
                        "Rol": u['rol'],
                        "Empresa": empresa_nombre
                    })
                
                st.dataframe(pd.DataFrame(flat_users), use_container_width=True)
            else:
                st.info("No hay usuarios registrados.")
        except Exception as e:
            st.warning(f"No se pudo cargar la lista de usuarios: {e}")
