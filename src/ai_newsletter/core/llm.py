from langchain_groq import ChatGroq

from src.ai_newsletter.core.config import get_settings

settings = get_settings()

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=settings.groq_api_key)
