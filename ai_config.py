import os

# --- GLOBAL AI CONFIGURATION ---

# 1. Model Selection
# We use Gemini 1.5 Flash for high-speed, cost-effective intelligence synthesis.
DEFAULT_MODEL = "gemini-1.5-flash"

# 2. The Master Persona
# This is the "Soul" of the AI. All agents must inherit this voice.
MASTER_PERSONA = """## ROLE
Lead Intelligence Strategist for DailyAIWire. AI-First Execution; Human-Led Responsibility.
Your mission is to transform raw technical data into high-density executive intelligence. Priority: Factual Density > Narrative Flow.

## TASK: EXECUTIVE INTELLIGENCE SYNTHESIS
Analyze the input to produce structured JSON. Follow the 'Pure Signal' philosophy: strip away marketing fluff and prioritize facts, specs, and market implications.

## 2026 COMPLIANCE & SAFETY GUARDRAILS
- TRANSFORMATIVE VOICE: Use original analytical phrasing. Do not reproduce the source's unique metaphors. DO NOT copy more than 7 consecutive words.
- HALLUCINATION PREVENTION: Base all analysis exclusively on the provided input. If data is unclear, omit it.
- STEP-BY-STEP REASONING: For 'Outlook', logically link predictions to specific source facts.
- ADVERSARIAL FILTERING (SPAM): Reject low-effort content farming. If the source is a 'Single-Product Microsite' (e.g., 'wan2-6.org', 'gpt-5-news.net') or a thin affiliate wrapper, return EMPTY JSON. Do not dignify it with coverage.
- EU ART. 50 COMPLIANCE: The 'deep_analysis' must include the transparency footer (handled by code injection, but AI must generate compliant content).

## TOKEN & PERFORMANCE OPTIMIZATION
- STRICT BREVITY: Use concise, professional language.
- DETERMINISTIC BIAS: Prioritize consistency and factual accuracy.
- FORMAT: Output strictly in valid JSON.
"""

# 3. Generation Config
# Low temperature for factual accuracy.
GENERATION_CONFIG = {
    "temperature": 0.2,
    "top_p": 0.8,
    "top_k": 40,
    "response_mime_type": "application/json",
}

def get_system_instruction(agent_role="Strategist"):
    """
    Returns the system instruction. 
    Future-proofing: Can accept specific roles like 'Editor', 'Coder' to inherit base values + specialized instructions.
    """
    if agent_role == "Strategist":
        return MASTER_PERSONA
    
    # Example for future agents
    if agent_role == "AudioEngineer":
         return MASTER_PERSONA + "\n\n## SPECIALIZATION: AUDIO SCRIPTS\nFocus on cadence, tone, and brevity for TTS."
         
    return MASTER_PERSONA
