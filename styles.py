import streamlit as st

def apply_login_styles():
    st.markdown("""
        <style>
            [data-testid="stAppViewContainer"] {
                background-color: #f8f9fa; 
            }
            .stButton>button {
                width: 100%;
                border-radius: 8px;
            }
        </style>
    """, unsafe_allow_html=True)

def apply_styles():
    st.markdown("""
        <style>
            /* IMPORTANTE: Estilos de los Tooltips */
            .tooltip-container {
                position: relative;
                display: inline-block;
                cursor: pointer;
                color: #2e6c80; /* Azulito corporativo para el número */
                font-weight: bold;
                border-bottom: 1px dotted #2e6c80;
            }

            /* El texto oculto (la cajita negra) */
            .tooltip-container .tooltip-text {
                visibility: hidden;
                width: 300px; /* Ancho de la caja */
                background-color: #333;
                color: #fff;
                text-align: left;
                border-radius: 6px;
                padding: 10px;
                font-size: 0.85rem;
                font-weight: normal;
                line-height: 1.4;
                
                /* Posicionamiento */
                position: absolute;
                z-index: 1000; /* Asegura que flote sobre todo */
                bottom: 125%; /* Que aparezca ARRIBA del número */
                left: 50%;
                margin-left: -150px; /* Centrado */
                
                /* Efecto de aparición */
                opacity: 0;
                transition: opacity 0.3s;
                box-shadow: 0px 4px 6px rgba(0,0,0,0.1);
            }

            /* Flechita decorativa abajo de la caja */
            .tooltip-container .tooltip-text::after {
                content: "";
                position: absolute;
                top: 100%;
                left: 50%;
                margin-left: -5px;
                border-width: 5px;
                border-style: solid;
                border-color: #333 transparent transparent transparent;
            }

            /* Mostrar al pasar el mouse */
            .tooltip-container:hover .tooltip-text {
                visibility: visible;
                opacity: 1;
            }

            /* Ajustes generales de la app */
            .stApp {
                background-color: #ffffff;
            }
        </style>
    """, unsafe_allow_html=True)
