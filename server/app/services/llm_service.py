import os
import re
import json
import httpx
from typing import Dict, Any, Optional

# OpenRouter API configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _get_openrouter_api_key() -> str:
    """Get OpenRouter API key from environment variables"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "your_openrouter_api_key_here":
        raise ValueError("OpenRouter API key is not configured. Please set OPENROUTER_API_KEY in your .env file.")
    return api_key


def _get_model(model: Optional[str] = None) -> str:
    """Get model name from environment variables"""
    return model or os.getenv("LLM_MODEL", "qwen/qwen3.6-flash")


def _format_openrouter_http_error(e: httpx.HTTPStatusError, model: str) -> str:
    """Return the most useful OpenRouter error message available."""
    try:
        error_body = e.response.json()
        message = error_body.get("error", {}).get("message")
        code = error_body.get("error", {}).get("code", e.response.status_code)
        if message:
            return f"OpenRouter API error {code} for model '{model}': {message}"
    except Exception:
        pass

    body_preview = e.response.text[:500] if e.response.text else ""
    if body_preview:
        return f"OpenRouter API error {e.response.status_code} for model '{model}': {body_preview}"
    return f"OpenRouter API error {e.response.status_code} for model '{model}': {str(e)}"


async def polish_sandbox_output(
    question: str,
    sandbox_output: str,
    execution_status: str,
    model: Optional[str] = None,
    structured_result: Optional[Dict[str, Any]] = None,
    evidence_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Polish sandbox execution output using LLM to provide a more natural language answer
    
    Args:
        question: Original user question
        sandbox_output: Raw output from sandbox execution
        execution_status: Execution status ('success' or 'error')
    
    Returns:
        Polished answer in natural language
    """
    try:
        # Check if output contains HTML table
        has_html_table = "<table" in sandbox_output.lower()
        
        # Build prompt for polishing
        table_instruction = ""
        if has_html_table:
            # Extract HTML table(s) to preserve them
            table_pattern = re.compile(r'<table[\s\S]*?</table>', re.IGNORECASE)
            html_tables = table_pattern.findall(sandbox_output)
            tables_text = "\n\n".join([f"[HTML Table {i+1}]:\n{table}" for i, table in enumerate(html_tables)])
            
            table_instruction = (
                f"\n\nIMPORTANT: The output contains HTML table(s). "
                f"Please preserve the exact HTML table(s) in your polished answer. "
                f"You can add explanation text before or after the table(s). "
                f"Here are the HTML tables that must be preserved:\n\n{tables_text}\n\n"
                f"Your polished answer should include these exact HTML tables along with your explanation."
            )
        
        report_result = dict(structured_result or {})
        if isinstance(report_result.get("datasets"), list):
            report_result["datasets"] = [
                {
                    "id": dataset.get("id"),
                    "name": dataset.get("name"),
                    "row_count": len(dataset.get("rows", [])),
                    "preview": dataset.get("rows", [])[:12],
                }
                for dataset in report_result["datasets"]
                if isinstance(dataset, dict)
            ]
        structured_text = json.dumps(report_result, ensure_ascii=False, indent=2)
        evidence_text = json.dumps(evidence_context or {}, ensure_ascii=False, indent=2)

        prompt = f"""The user asked: "{question}"

The sandbox execution produced the following output:

```
{sandbox_output}
```

Execution status: {execution_status}{table_instruction}

Validated structured result:
```json
{structured_text}
```

Metric and plan evidence:
```json
{evidence_text}
```

Please provide a polished, natural language answer based on the execution output. The answer should:
1. Directly address the user's question
2. Explain the result clearly and concisely
3. Be written in natural, conversational language
4. If the output contains tables, include the HTML tables exactly as provided and add explanation text around them
5. If the output contains structured data, summarize the key findings and explain what the data means
6. If there's an error, explain it in user-friendly terms
7. Be concise but comprehensive
8. Never introduce, estimate, round, or change a number that is not present in the user question, sandbox output, or structured result
9. Never claim causality when the evidence only shows association
10. State material assumptions or missing metric fields explicitly
11. Respond in the same language as the user's question

Provide your polished answer (preserving any HTML tables exactly as shown above):"""

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the reporting component of an evidence-first data analysis agent. "
                    "You may improve wording, but you must preserve every computed value and remain strictly grounded in the supplied artifact."
                )
            },
            {"role": "user", "content": prompt},
        ]
        
        # Use OpenRouter API
        api_key = _get_openrouter_api_key()
        model = _get_model(model)
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 1500
                }
            )
            response.raise_for_status()
            result = response.json()
            
            polished_content = result["choices"][0]["message"]["content"] or sandbox_output
            
            # If original output had HTML tables, ensure they are preserved in polished content
            if has_html_table:
                table_pattern = re.compile(r'<table[\s\S]*?</table>', re.IGNORECASE)
                original_tables = table_pattern.findall(sandbox_output)
                polished_tables = table_pattern.findall(polished_content)
                
                # If tables were lost during polishing, append them to the end
                if len(original_tables) > len(polished_tables):
                    missing_tables = original_tables[len(polished_tables):]
                    polished_content += "\n\n" + "\n\n".join(missing_tables)
                    print(f"[DEBUG] Restored {len(missing_tables)} HTML table(s) to polished output")
            
            return polished_content

    except httpx.HTTPStatusError as e:
        # If polishing fails, return original output
        print(f"[WARNING] Failed to polish sandbox output: {e}")
        return sandbox_output
    except Exception as e:
        # If any error occurs, return original output
        print(f"[WARNING] Error polishing sandbox output: {e}")
        return sandbox_output
