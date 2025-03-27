from dotenv import load_dotenv
import logging
import logging.config
from services import bedrock_agent_runtime
import streamlit as st



# General page configuration and initialization
#st.set_page_config(page_title=ui_title, page_icon=ui_icon, layout="wide")
st.subheader('RAG Using Knowledge Base & Agents from Amazon Bedrock', divider='rainbow')
st.markdown('WIP - This is a simple Agentic RAG application that leverage Amazon Bedrock Agent and Knowledge Base to answer questions.')
