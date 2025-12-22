import google.generativeai as genai
from services.supabase_db import supabase
from config import api_keys
import streamlit as st
import json

# Configuración básica
genai.configure(api_key=api_keys[0])

def get_embedding(text):
    """Convierte texto a vector."""
    try:
        result = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_query"
        )
        return result['embedding']
    except Exception as e:
        print(f"Error embedding: {e}")
        return None

def get_current_filters():
    """
    Extrae los filtros activos de la sesión de Streamlit.
    Retorna un diccionario estandarizado.
    """
    # Obtenemos los filtros del sidebar (según tu app.py)
    filters = {
        "marcas": sorted(st.session_state.get("filter_marcas", [])),
        "years": sorted(st.session_state.get("filter_years", [])),
        "projects": sorted(st.session_state.get("filter_projects", [])),
        # También es importante el cliente, para no mezclar datos entre empresas
        "client_context": st.session_state.get("cliente", "generico")
    }
    return filters

def check_semantic_cache(prompt, threshold=0.90): # Subimos un poco el threshold por seguridad
    try:
        vector = get_embedding(prompt)
        if not vector: return None

        # Obtenemos los filtros actuales
        current_filters = get_current_filters()

        response = supabase.rpc(
            "match_cached_response",
            {
                "query_embedding": vector,
                "match_threshold": threshold,
                "match_count": 1,
                "query_filters": current_filters # Enviamos los filtros a la query SQL
            }
        ).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]['bot_response']
        
        return None
    except Exception as e:
        print(f"Error caché: {e}")
        return None

def save_to_cache(prompt, response):
    try:
        if not response or "Error" in response: return

        vector = get_embedding(prompt)
        current_filters = get_current_filters() # Guardamos con los filtros activos

        if vector:
            data = {
                "user_prompt": prompt,
                "bot_response": response,
                "embedding": vector,
                "filters": current_filters # Guardar JSON
            }
            supabase.table("semantic_cache").insert(data).execute()
    except Exception as e:
        print(f"Error guardando caché: {e}")
