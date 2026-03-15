from core.models.model_gateway import ModelGateway
from core.prompts import MASTER_SYSTEM_PROMPT


class PlannerEngine:
    """
    Converts a user request + loaded project context into a structured plan.
    """

    def __init__(self):
        self.gateway = ModelGateway()

    def build_prompt(
        self,
        user_input: str,
        project_name: str,
        loaded_context: dict,
    ) -> str:
        docs = loaded_context.get("docs", "")
        memory = loaded_context.get("memory", "")
        tasks = loaded_context.get("tasks", "")

        return f"""
{MASTER_SYSTEM_PROMPT}

You are the Planner Engine inside FORGE AI STUDIO.

Your job:
- review the active project context
- understand the user's request
- produce a short structured implementation plan
- include an OPTIONAL patch_request only when a tiny exact-match patch is clearly safe

Active project: {project_name}

User request:
{user_input}

Project docs:
{docs}

Project memory:
{memory}

Project tasks:
{tasks}

Return ONLY JSON with this structure:

{{
  "objective": "...",
  "assumptions": ["..."],
  "implementation_steps": ["step1", "step2"],
  "risks": ["..."],
  "next_agent": "coder",
  "patch_request": null
}}

Or, only if a tiny exact patch is truly safe:

{{
  "objective": "...",
  "assumptions": ["..."],
  "implementation_steps": ["step1", "step2"],
  "risks": ["..."],
  "next_agent": "coder",
  "patch_request": {{
    "approved": true,
    "target_relative_path": "src/example.py",
    "search_text": "exact old text",
    "replacement_text": "exact new text",
    "replace_all": false,
    "justification": "brief reason"
  }}
}}

Rules:
- Return ONLY JSON
- No markdown
- No explanations outside JSON
- Keep implementation steps concise
- Prefer patch_request = null unless a tiny exact patch is clearly justified
- Never emit a broad or uncertain patch
"""

    def build_retry_prompt(
        self,
        previous_output: str,
        project_name: str,
        retry_reason: str,
    ) -> str:
        return f"""
{MASTER_SYSTEM_PROMPT}

You previously returned output for project "{project_name}" that could not be accepted.

Retry reason:
{retry_reason}

Previous output:
{previous_output[:4000]}

You must now repair this and return ONLY a valid JSON object.

Rules:
- Output ONLY JSON
- No markdown
- No code fences
- No commentary
- No prose before or after the JSON
- Ensure required keys exist:
  objective
  assumptions
  implementation_steps
  risks
  next_agent
  patch_request
- next_agent must be one of: "coder", "tester", "docs"
- patch_request must be null unless a tiny exact-match patch is clearly safe
"""

    def generate_raw_plan(
        self,
        user_input: str,
        project_name: str,
        loaded_context: dict,
        model: str = "gpt-5.4",
    ) -> str:
        prompt = self.build_prompt(
            user_input=user_input,
            project_name=project_name,
            loaded_context=loaded_context,
        )

        result = self.gateway.generate(
            prompt=prompt,
            provider="openai",
            model=model,
        )

        return result["output_text"]

    def retry_raw_plan(
        self,
        previous_output: str,
        project_name: str,
        retry_reason: str,
        model: str = "gpt-5.4",
    ) -> str:
        prompt = self.build_retry_prompt(
            previous_output=previous_output,
            project_name=project_name,
            retry_reason=retry_reason,
        )

        result = self.gateway.generate(
            prompt=prompt,
            provider="openai",
            model=model,
        )

        return result["output_text"]