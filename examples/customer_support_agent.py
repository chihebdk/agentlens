"""
Customer Support Agent — processes incoming support tickets.

This "agent" triages customer tickets, looks up order information,
drafts a response, and sends it. Built with LangGraph.
"""

import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


# ── State ────────────────────────────────────────────────────────────────────

class TicketState(TypedDict):
    ticket_id: str
    customer_email: str
    message: str
    category: str
    priority: str
    order_info: dict
    draft_response: str
    final_response: str
    sentiment: str


# ── LLM ──────────────────────────────────────────────────────────────────────

llm = ChatOpenAI(model="gpt-4o", temperature=0)


# ── Tools / Functions ────────────────────────────────────────────────────────

def lookup_order(order_id: str) -> dict:
    """Fetch order details from the orders database."""
    # Simulated DB lookup
    return {
        "order_id": order_id,
        "status": "shipped",
        "tracking": "1Z999AA10123456784",
        "estimated_delivery": "2025-04-02",
        "items": ["Wireless Mouse", "USB-C Hub"],
    }


def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via the email service."""
    # Simulated email send
    return {"status": "sent", "message_id": f"msg_{to[:5]}_12345"}


def log_ticket_resolution(ticket_id: str, category: str, resolution: str) -> dict:
    """Log the ticket resolution to the CRM system."""
    return {"logged": True, "ticket_id": ticket_id}


# ── Agent Nodes ──────────────────────────────────────────────────────────────

def analyze_sentiment(state: TicketState) -> dict:
    """Analyze customer sentiment to determine urgency."""
    response = llm.invoke([
        SystemMessage(content=(
            "You are a sentiment analyzer. Classify the customer message sentiment "
            "as one of: positive, neutral, frustrated, angry. "
            "Respond with ONLY the sentiment word."
        )),
        HumanMessage(content=state["message"]),
    ])
    return {"sentiment": response.content.strip().lower()}


def classify_ticket(state: TicketState) -> dict:
    """Classify the ticket into a category and priority."""
    response = llm.invoke([
        SystemMessage(content=(
            "You are a support ticket classifier. Given a customer message, classify it.\n\n"
            "Categories: billing, shipping, product_issue, account, general_inquiry\n"
            "Priority: low, medium, high, urgent\n\n"
            "Respond in this exact format:\n"
            "category: <category>\n"
            "priority: <priority>"
        )),
        HumanMessage(content=state["message"]),
    ])
    lines = response.content.strip().split("\n")
    category = lines[0].split(":")[1].strip()
    priority = lines[1].split(":")[1].strip()
    return {"category": category, "priority": priority}


def fetch_order_details(state: TicketState) -> dict:
    """Look up relevant order information if the ticket is about an order."""
    import re
    order_match = re.search(r"ORD-\d+", state["message"])
    if order_match:
        order_info = lookup_order(order_match.group())
    else:
        order_info = {"note": "No order ID found in message"}
    return {"order_info": order_info}


def draft_response(state: TicketState) -> dict:
    """Draft a response based on ticket category and order info."""
    response = llm.invoke([
        SystemMessage(content=(
            "You are a customer support agent. Draft a helpful, empathetic response "
            "to the customer based on the following context.\n\n"
            f"Category: {state['category']}\n"
            f"Priority: {state['priority']}\n"
            f"Sentiment: {state['sentiment']}\n"
            f"Order info: {state['order_info']}\n\n"
            "Keep the response concise (2-3 paragraphs). Be professional and helpful. "
            "If order tracking info is available, include it."
        )),
        HumanMessage(content=state["message"]),
    ])
    return {"draft_response": response.content}


def route_by_priority(state: TicketState) -> str:
    """Route based on priority — urgent tickets skip straight to send."""
    if state["priority"] == "urgent":
        return "send_response"
    return "review_and_refine"


def review_and_refine(state: TicketState) -> dict:
    """Review the draft and refine it for tone and completeness."""
    response = llm.invoke([
        SystemMessage(content=(
            "You are an editor reviewing a customer support response. "
            "Check for:\n"
            "1. Empathetic tone matching the customer sentiment\n"
            "2. All relevant order/account details included\n"
            "3. Clear next steps for the customer\n"
            "4. Professional formatting\n\n"
            "Output the final polished version of the response. "
            "Do not add commentary, just output the refined response."
        )),
        HumanMessage(content=f"Original customer message: {state['message']}\n\nDraft response: {state['draft_response']}"),
    ])
    return {"final_response": response.content}


def send_response(state: TicketState) -> dict:
    """Send the final response to the customer and log resolution."""
    response_text = state.get("final_response") or state["draft_response"]

    send_email(
        to=state["customer_email"],
        subject=f"Re: Support Ticket {state['ticket_id']}",
        body=response_text,
    )

    log_ticket_resolution(
        ticket_id=state["ticket_id"],
        category=state["category"],
        resolution=response_text[:200],
    )

    return {"final_response": response_text}


# ── Graph Assembly ───────────────────────────────────────────────────────────

graph = StateGraph(TicketState)

# Add nodes
graph.add_node("analyze_sentiment", analyze_sentiment)
graph.add_node("classify_ticket", classify_ticket)
graph.add_node("fetch_order_details", fetch_order_details)
graph.add_node("draft_response", draft_response)
graph.add_node("review_and_refine", review_and_refine)
graph.add_node("send_response", send_response)

# Define edges — the execution flow
graph.add_edge(START, "analyze_sentiment")
graph.add_edge("analyze_sentiment", "classify_ticket")
graph.add_edge("classify_ticket", "fetch_order_details")
graph.add_edge("fetch_order_details", "draft_response")
graph.add_conditional_edges(
    "draft_response",
    route_by_priority,
    {
        "review_and_refine": "review_and_refine",
        "send_response": "send_response",
    },
)
graph.add_edge("review_and_refine", "send_response")
graph.add_edge("send_response", END)

# Compile
app = graph.compile()


# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = app.invoke({
        "ticket_id": "TKT-20250330-001",
        "customer_email": "jane.doe@example.com",
        "message": (
            "Hi, I ordered a Wireless Mouse and USB-C Hub (order ORD-98765) "
            "last week and the tracking hasn't updated in 3 days. "
            "I'm really frustrated because I need these for work on Monday. "
            "Can someone please help?"
        ),
    })

    print(f"\n{'='*60}")
    print(f"Ticket: {result['ticket_id']}")
    print(f"Category: {result['category']}")
    print(f"Priority: {result['priority']}")
    print(f"Sentiment: {result['sentiment']}")
    print(f"{'='*60}")
    print(f"\nResponse sent:\n{result['final_response']}")
