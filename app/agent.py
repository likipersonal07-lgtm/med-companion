import os
import re
import sys
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from google.adk.agents import Agent, Context
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.workflow import Workflow, START, Edge, node
from google.adk.events import Event, RequestInput
from google.adk.tools import AgentTool, McpToolset
from google.genai import types
from mcp import StdioServerParameters

from app.config import config

# ─────────────────────────────────────────────────────────────────────────────
# STATE SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class CompanionState(BaseModel):
    patient_query: str = ""
    medications: List[str] = Field(default_factory=list)
    schedule_details: str = ""
    interaction_warnings: str = ""
    simplified_explanation: str = ""
    hitl_approved: Optional[bool] = None
    security_audit_log: List[str] = Field(default_factory=list)

class HITLApproval(BaseModel):
    approved: bool = Field(description="True if you acknowledge the drug interaction warnings and want to proceed, False otherwise.")
    notes: str = Field(description="Any additional notes or comments.", default="")

# ─────────────────────────────────────────────────────────────────────────────
# SUB-AGENTS & MCP DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

# Create the MCP Toolset connection
mcp_toolset = McpToolset(
    connection_params=StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
    )
)

# 1. Scheduler Agent
scheduler_agent = Agent(
    name="scheduler_agent",
    model=Gemini(model=config.model),
    instruction=(
        "You are a specialized medical scheduling assistant. Your job is to format the patient's daily medication schedule. "
        "Take the patient's medications and build a clear, structured daily schedule. "
        "Organize the schedule by morning, afternoon, evening, and bedtime. "
        "Include placeholder time ranges (e.g., Morning: 8:00 AM - 9:00 AM) and suggest taking medications with food or water where applicable. "
        "Keep your output structured, clear, and easy for a patient to read."
    )
)

# 2. Drug Interaction Checker Agent
interaction_agent = Agent(
    name="interaction_agent",
    model=Gemini(model=config.model),
    instruction=(
        "You are an expert pharmacology safety agent. Your job is to check for potential drug-to-drug interactions. "
        "Use the lookup_drug_interactions tool from the MCP server to check the drugs. "
        "Compare all the medications provided by the user. "
        "If you find any potential interactions, describe them and rate the severity as SEVERE, MODERATE, or MILD. "
        "If there are NSAID duplications (like Aspirin and Ibuprofen) or other unsafe combinations, you MUST highlight them and prefix the warning with 'SEVERE WARNING'. "
        "If no interactions are found, explicitly respond with: 'No drug interactions detected.'"
    ),
    tools=[mcp_toolset]
)

# 3. Patient Explainer Agent
explainer_agent = Agent(
    name="explainer_agent",
    model=Gemini(model=config.model),
    instruction=(
        "You are a warm, patient-friendly clinical communication agent. Your job is to translate complex medical information into simple language. "
        "You can use the get_drug_side_effects and get_dosage_guidelines tools from the MCP server to retrieve details about each drug. "
        "Receive the schedule and drug interaction warnings from the history/state. "
        "Provide a consolidated final summary. First, present the daily medication schedule clearly. "
        "Second, explain any drug interaction warnings in simple, reassuring, and jargon-free terms so the patient is not unnecessarily alarmed but is properly informed. "
        "Conclude with a warm, caring closing statement."
    ),
    tools=[mcp_toolset]
)

# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR & TOOLS
# ─────────────────────────────────────────────────────────────────────────────

def save_medication_details(ctx: Context, medications: List[str], schedule: str, interaction_warning: str = "") -> str:
    """Saves the extracted medications, formatted schedule, and drug interaction warnings to the session state.

    Args:
        medications: The list of drug names extracted from the query.
        schedule: The formatted daily medication schedule.
        interaction_warning: Any drug interaction warnings identified.
    """
    ctx.state['medications'] = medications
    ctx.state['schedule_details'] = schedule
    ctx.state['interaction_warnings'] = interaction_warning
    return "Successfully persisted medication details to state."

orchestrator = Agent(
    name="orchestrator",
    model=Gemini(model=config.model),
    instruction=(
        "You are the Med-Companion orchestrator agent. Your goal is to guide the user's medication intake safety analysis. "
        "You have access to three tools: scheduler_agent (to build a schedule), interaction_agent (to check drug interactions), "
        "and save_medication_details (to save the results to the state). "
        "Follow these steps exactly:\n"
        "1. Extract the names of the medications the user is asking about.\n"
        "2. Call the interaction_agent tool with the list of medications to check for safety.\n"
        "3. Call the scheduler_agent tool to format the daily schedule.\n"
        "4. Call save_medication_details to persist the extracted medications, the formatted schedule, and the interaction warnings to the state.\n"
        "5. Respond with a brief summary of what you found and state that the system is moving to the next node."
    ),
    tools=[
        AgentTool(scheduler_agent),
        AgentTool(interaction_agent),
        save_medication_details,
    ]
)

# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW NODES
# ─────────────────────────────────────────────────────────────────────────────

@node
def security_checkpoint(ctx: Context, node_input: Any):
    """Checks the query for prompt injections, PII, and medical abuse terms."""
    query = ""
    if isinstance(node_input, types.Content):
        parts = [p.text for p in node_input.parts if p.text]
        query = " ".join(parts)
    elif isinstance(node_input, str):
        query = node_input
    
    # 1. PII scrubbing (e.g. Social Security Numbers, Phone Numbers)
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    phone_pattern = r'\b\d{3}-\d{3}-\d{4}\b'
    
    sanitized_query = re.sub(ssn_pattern, "[REDACTED SSN]", query)
    sanitized_query = re.sub(phone_pattern, "[REDACTED PHONE]", sanitized_query)
    
    # 2. Prompt injection detection
    injection_keywords = [
        "ignore previous instructions", 
        "system prompt", 
        "override instructions", 
        "you must now act as"
    ]
    has_injection = any(kw in sanitized_query.lower() for kw in injection_keywords)
    
    # 3. Domain rule: Check if they are requesting illegal substances / dangerous advice
    dangerous_keywords = ["make poison", "recreational drugs", "abuse medication", "lethal dose"]
    has_dangerous = any(kw in sanitized_query.lower() for kw in dangerous_keywords)
    
    import json
    import datetime
    
    severity = "INFO"
    if has_injection or has_dangerous:
        severity = "CRITICAL"
    elif sanitized_query != query:
        severity = "WARNING"
        
    audit_log_entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "severity": severity,
        "pii_scrubbed": sanitized_query != query,
        "prompt_injection_detected": has_injection,
        "dangerous_query_detected": has_dangerous,
        "action": "block" if (has_injection or has_dangerous) else "allow"
    }
    
    # Update state log
    log = ctx.state.get("security_audit_log", [])
    log.append(json.dumps(audit_log_entry))
    ctx.state["security_audit_log"] = log
    
    if has_injection or has_dangerous:
        return Event(
            route="security_violation",
            output="Security Violation: The request was flagged as unsafe or contains a prompt injection attempt."
        )
        
    ctx.state["patient_query"] = sanitized_query
    return Event(route="clear", output=sanitized_query)


@node
def security_alert_node(ctx: Context, node_input: Any):
    """Handles security violations by returning a warning."""
    return f"⚠️ Security Alert: {node_input}"


@node(rerun_on_resume=True)
async def hitl_gate(ctx: Context):
    """Enforces human-in-the-loop review if a severe drug interaction warning is present."""
    if ctx.state.get("hitl_approved") is True:
        yield Event(route="proceed")
        return
    if ctx.state.get("hitl_approved") is False:
        yield Event(route="denied")
        return

    # Check if there is a severe warning
    warnings = ctx.state.get("interaction_warnings", "")
    if "SEVERE" not in warnings.upper():
        # No severe warning, auto-approve
        ctx.state["hitl_approved"] = True
        yield Event(route="proceed")
        return

    # Severe warning exists, check for resume input
    interrupt_id = f"hitl_approve_{ctx.run_id}"
    if interrupt_id in ctx.resume_inputs:
        resp = ctx.resume_inputs[interrupt_id]
        if resp.get("approved"):
            ctx.state["hitl_approved"] = True
            yield Event(route="proceed")
        else:
            ctx.state["hitl_approved"] = False
            yield Event(route="denied")
    else:
        # Yield RequestInput to trigger pause
        yield RequestInput(
            interrupt_id=interrupt_id,
            message=(
                f"⚠️ Severe Drug Interaction Warning Identified:\n\n{warnings}\n\n"
                "Please confirm if you acknowledge this warning and wish to proceed with generating the schedule."
            ),
            response_schema=HITLApproval,
        )


@node
def final_output(ctx: Context, node_input: Any):
    """Concludes the workflow and formats the final summary response."""
    approved = ctx.state.get("hitl_approved")
    if approved is False:
        return "❌ Request Cancelled: Daily medicine schedule could not be finalized because the drug interaction risks were not acknowledged."
    
    # If approved (or no warning), explainer_agent's output is passed as node_input
    return node_input

# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────

med_companion_workflow = Workflow(
    name="med_companion_workflow",
    state_schema=CompanionState,
    edges=[
        (START, security_checkpoint),
        Edge(from_node=security_checkpoint, to_node=orchestrator, route="clear"),
        Edge(from_node=security_checkpoint, to_node=security_alert_node, route="security_violation"),
        (orchestrator, hitl_gate),
        Edge(from_node=hitl_gate, to_node=explainer_agent, route="proceed"),
        Edge(from_node=hitl_gate, to_node=final_output, route="denied"),
        (explainer_agent, final_output),
    ]
)

# Main App entry point
app = App(
    root_agent=med_companion_workflow,
    name="app",
)
