import streamlit as st
import pandas as pd
import os
import re
from databricks import sql
from databricks.sdk import WorkspaceClient
from langchain_core.prompts import ChatPromptTemplate
from databricks_langchain import ChatDatabricks
from langchain.chains import LLMChain # Used for piping prompt and model

# --- 1. CONTEXT / CONFIGURATION LAYER (MCP PRINCIPLE) ---

class DatabricksContext:
    """Centralized configuration and connection logic for the application."""
    
    def __init__(self):
        # Programmatic cleanup for authentication conflict (CRITICAL FIX)
        # We prioritize PAT (token) over OAuth (client_id/secret)
        if "DATABRICKS_CLIENT_ID" in os.environ:
            del os.environ["DATABRICKS_CLIENT_ID"]
        if "DATABRICKS_CLIENT_SECRET" in os.environ:
            del os.environ["DATABRICKS_CLIENT_SECRET"]

        # Environment variables for PAT/Connection
        self.host = os.environ.get("DATABRICKS_HOST")
        self.http_path = os.environ.get("DATABRICKS_HTTP_PATH")
        self.token = os.environ.get("DATABRICKS_TOKEN")

        # Database schema constants
        self.catalog = "onedevcatalog"
        self.schema = "gold_one"
        self.tables = ["fact_table", "customer_dim", "item_dim", "store_dim", "time_dim", "transaction_dim"]
    
    def is_valid_pat_config(self):
        """Checks if PAT connection variables are present."""
        return all([self.host, self.http_path, self.token])

    @st.cache_resource(ttl=3600) 
    def get_sql_connection(_self): # <-- Changed 'self' to '_self'
        """Creates and caches the databricks.sql connection."""
        
        # NOTE: All internal references to 'self' must also be changed to '_self'
        if not _self.is_valid_pat_config():
            return None # Fail gracefully, UI will show error
        
        try:
            return sql.connect(
                server_hostname=_self.host, # Changed self.host to _self.host
                http_path=_self.http_path, # Changed self.http_path to _self.http_path
                access_token=_self.token # Changed self.token to _self.token
            )
        except Exception as e:
            st.error(f"Failed to initialize SQL connection: {e}")
            return None

    @st.cache_resource
    def get_workspace_client(_self): # Renamed 'self' to '_self'
        """Creates and caches the Databricks SDK client."""
        if not _self.host or not _self.token:
            return None
        # Must update all internal references from 'self' to '_self'
        return WorkspaceClient(host=_self.host, token=_self.token)

    @st.cache_resource
    def get_serving_endpoints(_self): # Renamed 'self' to '_self'
        """Fetches and caches the available serving endpoints."""
        # Must update all internal references from 'self' to '_self'
        w = _self.get_workspace_client() 
        if w:
            try:
                endpoints = w.serving_endpoints.list()
                return [endpoint.name for endpoint in endpoints]
            except Exception as e:
                st.error(f"Failed to list serving endpoints: {e}")
                return []
        return []

# --- 2. LOGIC LAYER (Separated Core Functions) ---

@st.cache_resource
def get_databricks_context():
    """Initializes and caches the application context (DatabricksContext)."""
    return DatabricksContext()

@st.cache_data(show_spinner=False)
def clean_sql(sql_text):
    """Cleans up LLM-generated SQL text."""
    sql_text = re.sub(r"```(?:sql)?\n", "", sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"```", "", sql_text)
    sql_text = "\n".join(line for line in sql_text.splitlines() if not line.strip().startswith("--"))
    return sql_text.strip()


def execute_sql_query(context: DatabricksContext, query: str) -> pd.DataFrame or None:
    """Executes a SQL query using the context's established connection."""
    conn = context.get_sql_connection()
    if conn is None:
        st.error("SQL connection is not active. Check configuration and token.")
        return pd.DataFrame()

    try:
        with conn.cursor() as cursor:
            st.info(f"Executing query: {query[:50]}...")
            cursor.execute(query)
            
            # Retrieve and convert data
            df = cursor.fetchall_arrow().to_pandas()
            
            st.success(f"Query executed successfully. Rows returned: {len(df):,}")
            return df
            
    except Exception as e:
        st.error(f"Error executing SQL query: {e}")
        return pd.DataFrame()


def build_llm_chains(context: DatabricksContext, model_name: str):
    """Builds and returns the LangChain chains for chat and query generation."""
    
    chat_model = ChatDatabricks(endpoint=model_name)
    
    # --- CHAT Template ---
    template_chat = "You are a helpful Databricks Expert. Answer the following question concisely.\nQuestion: {user_question}"
    prompt_template_chat = ChatPromptTemplate.from_template(template_chat)
    chat_chain = prompt_template_chat | chat_model

    # --- QUERY Template ---
    # Construct a robust prompt with the context's schema constants
    db_path = f"{context.catalog}.{context.schema}"
    table_list = ", ".join(context.tables)
    
    template_query = (
        f"You are a Data Agent with access to Databricks. Your database is {db_path} "
        f"and contains the following tables: {table_list}. "
        f"Translate the user request into a valid SQL query for Databricks. "
        f"Only return the SQL query, no explanations or commentary. "
        f"You MUST prefix all table names with the full path: `{context.catalog}.{context.schema}.`\n"
        f"User Request: {{user_question}}"
    )
    prompt_template_query = ChatPromptTemplate.from_template(template_query)
    query_chain = prompt_template_query | chat_model
    
    return chat_chain, query_chain


# --- 3. STREAMLIT UI/PRESENTATION LAYER ---

st.set_page_config(page_title="DBX AGENT", layout="wide")
st.title("DBX Chat & Data Agent")

# Initialize Context
CONTEXT = get_databricks_context()

# --- Status Check ---
if not CONTEXT.is_valid_pat_config():
    st.error("FATAL: Missing essential environment variables (HOST, HTTP_PATH, or TOKEN). Please check deployment config.")
    st.stop()
else:
    st.sidebar.success("Databricks Context and PAT Loaded.")


# Model Selection UI
endpoint_names = CONTEXT.get_serving_endpoints()
if not endpoint_names:
    st.error("No ready MLflow Serving Endpoints found. Cannot use LLM features.")
    st.stop()
    
model = st.selectbox("Select a Model", endpoint_names, index=0)

# Option Selection
options = st.selectbox("Select an Option", ["CHAT", "QUERY"], index=0)

# User Input
user_input = st.text_input("Enter your text", "How many customers do we have?")

# Build chains based on selected model
chat_chain, query_chain = build_llm_chains(CONTEXT, model)

if st.button("Submit"):
    st.markdown("---")
    
    if options == "CHAT":
        chain = chat_chain
        with st.spinner(f"Running CHAT with {model}..."):
            result = chain.invoke({"user_question": user_input})
            st.subheader("LLM Response")
            st.info(result.content)
    
    elif options == "QUERY":
        chain = query_chain
        
        # 1. Generate SQL
        with st.spinner(f"Generating SQL with {model}..."):
            sql_result = chain.invoke({"user_question": user_input})
            cleaned_sql = clean_sql(sql_result.content)
            
            st.subheader("Generated SQL")
            st.code(cleaned_sql, language="sql")

        # 2. Execute SQL
        with st.spinner("Executing query on Databricks..."):
            df_result = execute_sql_query(CONTEXT, cleaned_sql)
            
            if not df_result.empty:
                st.subheader("Query Result")
                st.dataframe(df_result)
            else:
                st.warning("Query returned no results or failed.")
    
    else:
        st.error("Invalid option selected.")
        
    st.success("Process Complete")