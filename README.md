# LLM Data Agent App on Databricks

This project implements a secure and modular Streamlit application deployed on the Databricks platform. It serves as a dual-purpose tool: a general LLM Chat Interface and a Data Agent capable of translating natural language queries into executable Databricks SQL, executing the query, and displaying the results.

The architecture emphasizes security, performance through caching, and maintainability through the adoption of the Model Context Protocol (MCP).

## 1\. Logical and Architectural Components

This application is built as a Databricks App, running directly on a Databricks SQL Warehouse or Compute Cluster.

|     |     |     |
| --- | --- | --- |
| Component | Role | Technologies Used |
| Streamlit UI | Frontend interface for model selection, input, and output display. | Python, Streamlit |
| Databricks Context (MCP) | Centralized configuration, authentication, and resource management. | Python Classes, @st.cache_resource |
| Authentication | Secure connection to Databricks services. | Personal Access Token (PAT) |
| LLM Chains | Uses Databricks Model Serving Endpoints to handle two distinct tasks. | LangChain (ChatDatabricks), ChatPromptTemplate |
| SQL Execution | Runs the LLM-generated SQL query against the Unity Catalog tables. | databricks.sql connector |

### Data Schema Used

The application targets a specific Unity Catalog path: onedevcatalog.gold_one with the following dimensional model tables: fact_table, customer_dim, item_dim, store_dim, time_dim, and transaction_dim.

## 2\. Technical Components and Implementation

### 2.1 Model Context Protocol (MCP) Implementation

The core principle for achieving clean, maintainable, and cacheable code is the Model Context Protocol (MCP).

1.  Centralized Context (DatabricksContext Class):

- Holds all static configuration (catalog/schema names) and sensitive credentials (Host, HTTP Path, Token) read from environment variables.
    
- Encapsulates resource initialization methods (get_sql_connection, get_workspace_client).
    

2.  Caching (@st.cache_resource): Critical expensive resources (connection objects, WorkspaceClient, list of endpoints) are cached using st.cache_resource to prevent re-initialization on every user interaction, significantly boosting performance.
    
3.  Dependency Injection: Core functions (execute_sql_query, build_llm_chains) explicitly require a DatabricksContext object as their first argument (context). This makes dependencies clear and simplifies testing.
    

### 2.2 Secure Authentication Flow

The application relies on PAT Authentication for connecting to Databricks services (both SQL and Model Serving API).

- Conflict Resolution: The application begins by programmatically deleting conflicting environment variables (DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET) using os.environ.pop() to guarantee the robust PAT method is used, avoiding the ValueError: more than one authorization method configured.
    
- Security: All sensitive credentials (DATABRICKS_TOKEN, DATABRICKS_HTTP_PATH) are loaded from the secure environment variables managed by the Databricks deployment, ensuring no secrets are hardcoded.
    

### 2.3 LLM Chains for Dual Functionality (LangChain Deep Dive)

This project leverages LangChain to create modular, reusable components for interacting with the LLM, showcasing proficiency in chain construction and component management.

1.  Model Integration (ChatDatabricks):

- The ChatDatabricks class is used as the standard LLM interface, abstracting the complexities of calling the specific Databricks Model Serving API endpoint. This maintains portability across different models available in the workspace (e.g., Llama 3, DBRX).

2.  Prompt Template Management (ChatPromptTemplate):

- Two distinct ChatPromptTemplate objects are defined, one for general chat (template_chat) and one for SQL generation (template_query).
    
- This separation ensures that the LLM is given a clean, task-specific persona and constraints (e.g., listing the schema, requiring table prefixes) without mixing instructions.
    

3.  Simple Chain Construction (Piping):

- The final logic uses the concise LangChain Expression Language (LCEL) piping syntax (prompt_template | chat_model) to construct the chains (chat_chain, query_chain). This demonstrates an efficient pattern for creating sequential components where the output of the prompt template is directly fed as input to the model.

|     |     |     |
| --- | --- | --- |
| Chain Name | Purpose | Agentic Role |
| CHAT Chain | General conversational QA (e.g., explaining concepts). | Knowledge Expert (Retrieval/Summary) |
| QUERY Chain | Converts natural language to runnable SQL. | Action Planner (Tool Specification) |

### 2.4 Agentic Capabilities and Tool Use

The QUERY Chain and its subsequent execution showcase an effective Agentic workflow:

1.  Tool Definition: The execute_sql_query function is the agent's Data Access Tool. It provides the sole mechanism for the agent to interact with the environment (the Databricks database).
    
2.  Structured Reasoning (Planning): The agent (LLM) is provided with explicit constraints (catalog/schema names) and rules (the requirement to prefix all tables) in the prompt. This forces the LLM to output a structured plan (the SQL code) that conforms to the tool's requirements.
    
3.  Action Initiation: The Streamlit app receives the SQL plan, cleans it (clean_sql), and passes it to the execute_sql_query tool.
    
4.  Action Execution: The tool (the function) securely connects to Databricks and runs the generated code.
    
5.  Result Integration: The DataFrame output is returned to the Streamlit UI, completing the Perception-Reasoning-Action-Feedback loop required for an effective agent.
    

## 3\. Key Learning Highlights and Challenges Overcome

During the development of this robust application, several key challenges related to environment and dependency interaction were resolved:

1.  Resolving Connection Hangs: The initial attempt using OAuth (Service Principal) failed due to deployment complexities, resulting in non-terminating queries. Switching to PAT authentication (using access_token in databricks.sql.connect()) proved to be the reliable solution for in-cluster apps.
    
2.  Handling Authentication Conflicts: Debugging the ValueError: more than one authorization method configured required explicitly removing conflicting OAuth variables from the os.environ to force the databricks-sdk and databricks.sql to use the working PAT.
    
3.  Streamlit Caching on Class Methods: Successfully implementing caching (@st.cache_resource) on class methods (get_sql_connection, get_serving_endpoints, get_workspace_client) required changing the self argument to \_self to bypass the UnhashableParamError.
    
4.  Databricks SDK Versioning: Correctly parsing the Model Serving endpoint status required debugging the SDK object structure, finding that endpoint.state.current was outdated and replacing it with more robust checks to confirm STATE_READY.
    

\*\*