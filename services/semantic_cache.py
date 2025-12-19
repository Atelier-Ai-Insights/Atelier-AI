import google.generativeai as genai
from services.supabase_db import supabase
from config import api_keys
import streamlit as st

# Configuración básica (usa la primera llave disponible para embeddings, son muy baratos/gratis)
genai.configure(api_key=api_keys[0])

def get_embedding(text):
    """Convierte texto a vector numérico usando Gemini."""
    try:
        # Usamos el modelo embedding-001 optimizado para esto
        result = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_query"
        )
        return result['embedding']
    except Exception as e:
        print(f"Error generando embedding: {e}")
        return None

def check_semantic_cache(prompt, threshold=0.85):
    """
    Busca si existe una respuesta similar en la BD.
    threshold=0.85 significa 85% de similitud semántica.
    """
    try:
        vector = get_embedding(prompt)
        if not vector: return None

        response = supabase.rpc(
            "match_cached_response",
            {
                "query_embedding": vector,
                "match_threshold": threshold,
                "match_count": 1
            }
        ).execute()

        if response.data and len(response.data) > 0:
            # ¡ÉXITO! Encontramos una respuesta guardada
            print(f"✅ Cache Hit! Similitud: {response.data[0]['similarity']:.2f}")
            return response.data[0]['bot_response']
        
        return None
    except Exception as e:
        print(f"Error consultando caché: {e}")
        return None

def save_to_cache(prompt, response):
    """Guarda la nueva interacción en Supabase para el futuro."""
    try:
        # No guardamos respuestas de error o vacías
        if not response or "Error" in response: return

        vector = get_embedding(prompt)
        if vector:
            data = {
                "user_prompt": prompt,
                "bot_response": response,
                "embedding": vector
            }
            supabase.table("semantic_cache").insert(data).execute()
    except Exception as e:
        print(f"Error guardando en caché: {e}")
