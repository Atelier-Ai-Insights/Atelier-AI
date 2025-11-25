def show_otp_verification_page(otp_code, context="recovery"):
    """
    Verifica el código OTP que llega por URL.
    Sirve para 'invite' (signup) y 'recovery'.
    """
    st.header("Verificación de Seguridad")
    
    if context == "invite":
        st.info("Para activar tu invitación, confirma tu correo electrónico.")
        btn_label = "Validar y Activar"
        otp_type = "signup" # Ojo: Supabase usa 'signup' o 'invite' dependiendo de la versión, 'invite' suele funcionar mejor para API admin. 
        # Probaremos con 'invite' primero, que es el standard para MagicLinks de admin.
        otp_type_api = "invite" 
    else:
        st.write("Confirma tu correo para restablecer tu contraseña.")
        btn_label = "Verificar"
        otp_type_api = "recovery"

    email_verify = st.text_input("Confirma tu Correo Electrónico")
    
    if st.button(btn_label, width='stretch', type="primary"):
        if not email_verify:
            st.warning("Debes ingresar tu correo.")
            return
        try:
            # Intentamos verificar el OTP
            res = supabase.auth.verify_otp({
                "email": email_verify,
                "token": otp_code,
                "type": otp_type_api
            })
            
            if res.session:
                # Si hay sesión, guardamos y redirigimos al cambio de password
                st.session_state.access_token = res.session.access_token
                st.session_state.refresh_token = res.session.refresh_token
                
                # Redirigimos internamente a la pantalla de Set Password
                # No hacemos rerun aún para no perder el estado, forzamos la UI
                st.success("¡Verificado! Configurando cuenta...")
                time.sleep(1)
                # Guardamos flags para que app.py sepa qué mostrar
                st.session_state['temp_auth_verified'] = True
                st.session_state['temp_auth_type'] = context
                st.rerun()
            else:
                st.error("El código no es válido o ha expirado.")
        except Exception as e:
            # Fallback: A veces 'invite' falla y es 'signup' (depende de configuración)
            if context == "invite" and "type" in str(e):
                try:
                    res = supabase.auth.verify_otp({"email": email_verify, "token": otp_code, "type": "signup"})
                    if res.session:
                        st.session_state.access_token = res.session.access_token
                        st.session_state.refresh_token = res.session.refresh_token
                        st.session_state['temp_auth_verified'] = True
                        st.session_state['temp_auth_type'] = context
                        st.rerun()
                        return
                except: pass
            st.error(f"Error de verificación: {e}")
