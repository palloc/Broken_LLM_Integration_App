import re

from langchain.utilities.sql_database import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_experimental.sql import SQLDatabaseChain

from .settings import settings
from .llm_models import *


class SQLGenerationRefused(ValueError):
    pass


class SQLCodeOutputParser(StrOutputParser):
    def parse(self, text: str) -> str:
        if text.strip().startswith("SQLQuery:"):
            text = text.strip().removeprefix("SQLQuery:").split("SQLResult:", 1)[0].strip()
        fenced = re.fullmatch(r"```(?:sql)?\s*\n(.*?)\n```", text.strip(), re.DOTALL)
        parsed = fenced.group(1) if fenced else text
        if parsed.strip().rstrip(";").upper() == "REFUSE":
            raise SQLGenerationRefused("REFUSE")
        return parsed


# Create DB chain.
def create_db_chain():
    db = SQLDatabase.from_uri(settings.DB_DATABASE_URL)
    chain = SQLDatabaseChain.from_llm(
        llm=create_chat_openai_model(),
        db=db,
        verbose=settings.SQL_CHAIN_VERBOSE
    )
    chain.llm_chain.output_parser = SQLCodeOutputParser()
    return chain

# Execute SQL query.
def run_sql_chain(query: str) -> str:
    db_chain = create_db_chain()
    db_chain.return_intermediate_steps = True
    try:
        result = db_chain.invoke({"query": query})
    except SQLGenerationRefused:
        return "SQLQuery: REFUSE\nAnswer: REFUSE"
    steps = result["intermediate_steps"]
    sql_query = steps[1].split("SQLQuery:")[-1].split("SQLResult:")[0].strip()
    return f"SQLQuery: {sql_query}\nSQLResult: {steps[3]}\nAnswer: {result['result']}"
