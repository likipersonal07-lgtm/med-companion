import sys
from mcp.server.fastmcp import FastMCP

# Create an MCP server named "med-companion"
mcp = FastMCP("med-companion")

@mcp.tool()
def lookup_drug_interactions(drugs: list[str]) -> str:
    """Checks for potential interactions between a list of drug names.

    Args:
        drugs: A list of drug names (case-insensitive) to check for interactions.
    """
    normalized_drugs = {d.strip().lower() for d in drugs}
    
    warnings = []
    
    # Check for Aspirin + Ibuprofen
    if "aspirin" in normalized_drugs and "ibuprofen" in normalized_drugs:
        warnings.append(
            "SEVERE WARNING: Aspirin and Ibuprofen are both Nonsteroidal Anti-inflammatory Drugs (NSAIDs). "
            "Taking them together increases the risk of serious gastrointestinal side effects, including inflammation, "
            "bleeding, and ulceration."
        )
        
    # Check for Warfarin + Aspirin
    if "warfarin" in normalized_drugs and "aspirin" in normalized_drugs:
        warnings.append(
            "SEVERE WARNING: Warfarin (anticoagulant) and Aspirin (antiplatelet) both thin the blood. "
            "Co-administration significantly increases the risk of major, potentially life-threatening bleeding events."
        )
        
    # Check for Lisinopril + Spironolactone
    if "lisinopril" in normalized_drugs and "spironolactone" in normalized_drugs:
        warnings.append(
            "MODERATE WARNING: Lisinopril (ACE inhibitor) and Spironolactone (potassium-sparing diuretic) both increase potassium levels. "
            "Taking them together can cause hyperkalemia (high blood potassium), which can lead to serious cardiac issues."
        )
        
    # Check for Amoxicillin + Methotrexate
    if "amoxicillin" in normalized_drugs and "methotrexate" in normalized_drugs:
        warnings.append(
            "MILD WARNING: Amoxicillin may decrease the renal clearance of Methotrexate, potentially increasing methotrexate blood levels "
            "and toxicity. Regular monitoring is recommended."
        )
        
    if warnings:
        return "\n\n".join(warnings)
        
    return "No drug interactions detected between the provided medications."

@mcp.tool()
def get_drug_side_effects(drug: str) -> str:
    """Retrieves the standard clinical side effect profile for a given drug.

    Args:
        drug: The name of the drug (e.g. Aspirin, Lisinopril).
    """
    d = drug.strip().lower()
    
    profiles = {
        "aspirin": "Common side effects: Dyspepsia, nausea, increased bleeding tendency. Less common but serious: Gastrointestinal ulceration, tinnitus, allergic reactions.",
        "ibuprofen": "Common side effects: Heartburn, nausea, dizziness, headache, abdominal pain. Less common but serious: GI bleeding, renal impairment, fluid retention.",
        "warfarin": "Common side effects: Easy bruising, minor bleeding (nosebleeds, gum bleeding). Serious: Severe hemorrhaging, purple toes syndrome, tissue necrosis.",
        "lisinopril": "Common side effects: Dry cough, dizziness, headache, hypotension. Less common but serious: Angioedema, hyperkalemia, renal dysfunction.",
        "spironolactone": "Common side effects: Hyperkalemia, gynecomastia, breast tenderness, dizziness, electrolyte imbalance. Serious: Severe arrhythmia due to hyperkalemia.",
        "amoxicillin": "Common side effects: Diarrhea, nausea, vomiting, skin rash. Serious: Anaphylaxis, Clostridioides difficile-associated diarrhea."
    }
    
    return profiles.get(d, f"No detailed side effect profile found for '{drug}'. Typical general side effects may include mild nausea, headache, or dizziness. Consult a pharmacist.")

@mcp.tool()
def get_dosage_guidelines(drug: str) -> str:
    """Retrieves standard adult dosage guidelines for a given drug.

    Args:
        drug: The name of the drug.
    """
    d = drug.strip().lower()
    
    guidelines = {
        "aspirin": "Standard Adult Dosage:\n- Pain/Fever: 325mg to 650mg every 4 to 6 hours as needed (Max 4g/day).\n- Cardio-protection: 81mg to 325mg once daily.",
        "ibuprofen": "Standard Adult Dosage:\n- Pain/Fever: 200mg to 400mg every 4 to 6 hours as needed (Max 1200mg/day over-the-counter; up to 3200mg/day under medical supervision).",
        "warfarin": "Standard Adult Dosage:\n- Dosing is highly individualized. Typically starts at 2mg to 5mg once daily. Dosage is adjusted based on regular International Normalized Ratio (INR) blood tests.",
        "lisinopril": "Standard Adult Dosage:\n- Hypertension: 10mg once daily initially, maintenance dosage 20mg to 40mg once daily.",
        "spironolactone": "Standard Adult Dosage:\n- Heart Failure: 25mg once daily.\n- Hypertension/Edema: 25mg to 100mg daily in single or divided doses.",
        "amoxicillin": "Standard Adult Dosage:\n- Infections: 250mg to 500mg every 8 hours, or 500mg to 875mg every 12 hours, depending on severity."
    }
    
    return guidelines.get(d, f"No standard dosage guidelines found for '{drug}'. Dosage must be determined individually by a healthcare provider.")

if __name__ == "__main__":
    mcp.run()
