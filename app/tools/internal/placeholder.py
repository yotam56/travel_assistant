from langchain.tools import tool


# TODO: Replace with actual internal DB retrieval logic
@tool
def retrieve_from_db(query: str) -> str:
    """Search the internal travel database for relevant information.
    Use this when the user asks about saved trips, bookings, or stored preferences."""
    return f"[placeholder] No results found for '{query}'. Internal DB not yet connected."
