"""
Code generation and execution service
"""

import os
import re
import json
import ast
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx

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


def contains_image_generation(code: str) -> bool:
    """
    Check if code contains matplotlib or seaborn image generation.
    
    Args:
        code: Python code string to check
        
    Returns:
        True if code likely generates images, False otherwise
    """
    if not code:
        return False
    
    code_lower = code.lower()
    
    # Check for matplotlib imports (common patterns)
    matplotlib_import_patterns = [
        r'import\s+matplotlib',
        r'from\s+matplotlib',
        r'matplotlib\.pyplot',
        r'from\s+pylab',
    ]
    
    # Check for seaborn imports
    seaborn_import_patterns = [
        r'import\s+seaborn',
        r'from\s+seaborn',
        r'import\s+sns\s*$',
    ]

    other_rendering_patterns = [
        r'import\s+plotly',
        r'from\s+plotly',
        r'import\s+PIL',
        r'from\s+PIL',
        r'import\s+graphviz',
        r'from\s+graphviz',
        r'plotly\.',
        r'\bpx\.(bar|line|scatter|histogram|box|imshow|pie)\s*\(',
        r'\bgo\.Figure\s*\(',
        r'\.write_image\s*\(',
        r'\.render\s*\(',
    ]
    
    # Check for image generation/display functions (more specific patterns)
    image_generation_patterns = [
        r'plt\.show\s*\(',
        r'plt\.savefig\s*\(',
        r'figure\.show\s*\(',
        r'fig\.show\s*\(',
        r'plt\.imshow\s*\(',
        r'plt\.figure\s*\(',
        r'seaborn\.',
        r'sns\.(plot|barplot|lineplot|scatterplot|histplot|boxplot|violinplot|heatmap|pairplot|jointplot)',
        r'plt\.(plot|bar|hist|scatter|pie|boxplot|violinplot|heatmap)\s*\(',
        r'plt\.subplot\s*\(',
        r'plt\.subplots\s*\(',
        r'plt\.gca\s*\(',
        r'plt\.gcf\s*\(',
    ]
    
    # Check for matplotlib/seaborn imports using regex for more accurate matching
    has_matplotlib = any(re.search(pattern, code, re.IGNORECASE | re.MULTILINE) for pattern in matplotlib_import_patterns)
    has_seaborn = any(re.search(pattern, code, re.IGNORECASE | re.MULTILINE) for pattern in seaborn_import_patterns)
    
    # Check for image generation patterns
    has_image_patterns = any(re.search(pattern, code, re.IGNORECASE) for pattern in image_generation_patterns)
    has_other_rendering = any(re.search(pattern, code, re.IGNORECASE | re.MULTILINE) for pattern in other_rendering_patterns)

    if has_other_rendering:
        return True
    
    # If code imports matplotlib/seaborn AND has plotting functions, it's likely generating images
    if (has_matplotlib or has_seaborn) and has_image_patterns:
        return True
    
    # Also check if there are plotting patterns that strongly indicate image generation
    # (like plt.show() or plt.savefig() which are almost always for images)
    strong_image_indicators = [
        r'plt\.show\s*\(',
        r'plt\.savefig\s*\(',
        r'figure\.show\s*\(',
        r'fig\.show\s*\(',
    ]
    if any(re.search(pattern, code, re.IGNORECASE) for pattern in strong_image_indicators):
        return True
    
    return False


def _is_valid_python(candidate: str) -> bool:
    if not candidate.strip():
        return False
    try:
        ast.parse(candidate)
        return True
    except SyntaxError:
        return False


def _message_text(message: Dict[str, Any]) -> str:
    """Normalize OpenAI-compatible string or content-block responses."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _extract_code_and_reasoning(full_response: str) -> Dict[str, str]:
    """Extract only syntactically valid Python from common model response shapes."""
    response = (full_response or "").strip()
    if not response:
        return {"code": "", "thinking_process": ""}

    # Some providers follow the structured-output instruction even when it was
    # supplied only in prose.
    try:
        payload = json.loads(response)
        if isinstance(payload, dict) and isinstance(payload.get("code"), str):
            candidate = payload["code"].strip()
            if _is_valid_python(candidate):
                return {
                    "code": candidate,
                    "thinking_process": str(payload.get("reasoning_summary", "")).strip(),
                }
    except json.JSONDecodeError:
        pass

    fenced_matches = list(re.finditer(
        r"```(?:python|py)?\s*\r?\n([\s\S]*?)```",
        response,
        flags=re.IGNORECASE,
    ))
    for match in fenced_matches:
        candidate = match.group(1).strip()
        if _is_valid_python(candidate):
            summary = "\n\n".join(
                part for part in (response[:match.start()].strip(), response[match.end():].strip())
                if part
            )
            return {"code": candidate, "thinking_process": summary}

    # Never execute hidden thinking blocks as Python.
    visible = re.sub(r"<think>[\s\S]*?</think>", "", response, flags=re.IGNORECASE).strip()
    if _is_valid_python(visible):
        return {"code": visible, "thinking_process": ""}

    # Handle a short explanation followed by unfenced code.
    lines = visible.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^\s*(?:from\s+\S+\s+import|import\s+\S+|def\s+\w+|class\s+\w+)", line):
            candidate = "\n".join(lines[index:]).strip()
            if _is_valid_python(candidate):
                return {
                    "code": candidate,
                    "thinking_process": "\n".join(lines[:index]).strip(),
                }

    return {"code": "", "thinking_process": visible}


async def _request_code_completion(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
) -> Dict[str, str]:
    """Request executable code and retry once when a provider returns no final content."""
    attempts = [
        {"max_tokens": 4000, "strict_suffix": ""},
        {
            "max_tokens": 6000,
            "strict_suffix": (
                "\n\nYour previous response did not contain executable Python. "
                "Return complete syntactically valid Python in one ```python fenced block. "
                "Do not return only reasoning, a plan, or an empty response."
            ),
        },
    ]
    last_finish_reason = None
    last_usage: Dict[str, Any] = {}

    for attempt in attempts:
        request_messages = [dict(message) for message in messages]
        request_messages[-1]["content"] += attempt["strict_suffix"]
        response = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": request_messages,
                "temperature": temperature,
                "max_tokens": attempt["max_tokens"],
                # Code generation needs final executable output, not a hidden
                # reasoning trace consuming the completion budget.
                "reasoning": {"effort": "none", "exclude": True},
            },
        )
        response.raise_for_status()
        result = response.json()
        choice = result.get("choices", [{}])[0]
        message = choice.get("message") or {}
        parsed = _extract_code_and_reasoning(_message_text(message))
        if parsed["code"]:
            return parsed
        last_finish_reason = choice.get("finish_reason")
        last_usage = result.get("usage") or {}

    completion_tokens = last_usage.get("completion_tokens", "unknown")
    raise ValueError(
        "No executable Python returned after one retry "
        f"(finish_reason={last_finish_reason}, completion_tokens={completion_tokens})"
    )


async def generate_code(
    question: str,
    file_headers: List[Dict[str, Any]],
    prompt_style: str = "zero",
    model: Optional[str] = None,
    analysis_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate Python code from question and file headers, returns both code and thinking process"""
    try:
        prompt = _build_code_generation_prompt(question, file_headers, prompt_style, analysis_context)
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the execution-code component of an evidence-first data analysis agent. "
                    "Generate complete pandas code that follows the supplied plan and emits the required structured result marker. "
                    "Do not invent columns, filters, business definitions, or computed values."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Use OpenRouter API
        api_key = _get_openrouter_api_key()
        model = _get_model(model)
        async with httpx.AsyncClient(timeout=120.0) as client:
            parsed_response = await _request_code_completion(
                client=client,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=0.2,
            )

        code = parsed_response["code"]
        thinking_process = parsed_response["thinking_process"]
        
        if not code:
            raise ValueError("No code generated from LLM")
        
        return {
            "code": code,
            "thinking_process": thinking_process
        }
    except httpx.HTTPStatusError as e:
        model = _get_model(model)
        error_message = "Code generation failed"
        if e.response.status_code == 429:
            error_message = "OpenRouter API quota exceeded. Please check your billing and plan details."
        elif e.response.status_code == 401:
            error_message = "Invalid OpenRouter API key. Please check your API key in .env file"
        elif e.response.status_code == 402:
            error_message = "Insufficient credits. Please add credits to your OpenRouter account."
        elif e.response.status_code == 403:
            error_message = _format_openrouter_http_error(e, model)
        else:
            error_message = _format_openrouter_http_error(e, model)
        raise ValueError(error_message)
    except Exception as e:
        error_message = f"Code generation failed: {str(e)}"
        raise ValueError(error_message)


async def repair_code(
    question: str,
    file_headers: List[Dict[str, Any]],
    previous_code: str,
    execution_error: str,
    prompt_style: str = "zero",
    attempt_number: int = 1,
    model: Optional[str] = None,
    analysis_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Repair generated Python code using sandbox execution feedback."""
    try:
        prompt = _build_code_repair_prompt(
            question=question,
            file_headers=file_headers,
            previous_code=previous_code,
            execution_error=execution_error,
            prompt_style=prompt_style,
            attempt_number=attempt_number,
            analysis_context=analysis_context,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior Python data analysis engineer. "
                    "Your job is to repair failed pandas code using the execution error. "
                    "Return complete executable Python code in a markdown code block."
                )
            },
            {"role": "user", "content": prompt}
        ]

        api_key = _get_openrouter_api_key()
        model = _get_model(model)
        async with httpx.AsyncClient(timeout=120.0) as client:
            parsed_response = await _request_code_completion(
                client=client,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=0.1,
            )

        code = parsed_response["code"]
        thinking_process = parsed_response["thinking_process"]

        if not code:
            raise ValueError("No repaired code generated from LLM")

        return {
            "code": code,
            "thinking_process": thinking_process
        }
    except httpx.HTTPStatusError as e:
        model = _get_model(model)
        error_message = _format_openrouter_http_error(e, model)
        if e.response.status_code == 429:
            error_message = "OpenRouter API quota exceeded during code repair."
        elif e.response.status_code == 401:
            error_message = "Invalid OpenRouter API key during code repair."
        elif e.response.status_code == 402:
            error_message = "Insufficient OpenRouter credits during code repair."
        raise ValueError(error_message)
    except Exception as e:
        raise ValueError(f"Code repair failed: {str(e)}")


def _build_code_generation_prompt(
    question: str,
    file_headers: List[Dict[str, Any]],
    prompt_style: str = "zero",
    analysis_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Build prompt for code generation with different styles"""
    prompt = "Generate Python code to answer the user's question by analyzing CSV data. The question may be in any language (English, Chinese, etc.) - understand it and generate appropriate code.\n\n"
    
    prompt += "## Available CSV Files:\n\n"
    for index, file in enumerate(file_headers, 1):
        file_id = file['fileId']
        prompt += f"### File {index}: {file['fileName']}\n"
        prompt += f"- File ID: {file_id}\n"
        prompt += f"- File Path: {file_id}.csv (CRITICAL: use this EXACT filename '{file_id}.csv' to read the file)\n"
        prompt += f"- Columns: {', '.join(file['headers'])}\n"
        prompt += f"- Total Rows: {file['rows']}\n"
        prompt += f"- Total Columns: {file['columns']}\n\n"
        if file.get("profile"):
            prompt += "- Dataset Profile:\n"
            prompt += json.dumps(file["profile"], ensure_ascii=False, indent=2) + "\n\n"

    if analysis_context:
        prompt += "## Grounded Analysis Context:\n"
        prompt += json.dumps(analysis_context, ensure_ascii=False, indent=2) + "\n\n"
    
    prompt += f"## User Question:\n{question}\n\n"
    
    # Add prompt style specific instructions
    if prompt_style == "zero":
        # Zero-shot: Direct question asking for the answer
        prompt += "What is the answer? \n\n"
    elif prompt_style == "zero_cot":
        # Zero-shot CoT: Think step by step
        prompt += "Let's think step by step.\n"
        # prompt += "1. First, understand what the question is asking\n"
        # prompt += "2. Then, identify what data analysis is needed\n"
        # prompt += "3. Finally, generate Python code to find the answer\n\n"
        prompt += "Please provide your reasoning for each step before the code.\n\n"
    elif prompt_style == "sub_question":
        # Sub-Question Decomposition: Break into smaller questions
        prompt += "Please break the question into several smaller sub-questions. "
        prompt += "For each sub-question, explain how you will answer it, then provide the Python code. "
        prompt += "Finally, combine all answers to get the final result.\n\n"
        prompt += "Please show your sub-question decomposition and reasoning before the code.\n\n"
    
    prompt += "## Requirements:\n"
    prompt += "1. Import only calculation libraries such as pandas, numpy, scipy, or scikit-learn. Do NOT import matplotlib, seaborn, plotly, PIL, graphviz, or any image/rendering library\n"
    if file_headers:
        exact_file_id = file_headers[0]['fileId']
        prompt += f"2. Read the CSV file(s) using pandas with the EXACT filename: df = pd.read_csv('{exact_file_id}.csv')\n"
        prompt += f"   IMPORTANT: The filename must be exactly '{exact_file_id}.csv' (case-sensitive, no extra spaces or characters)\n"
    prompt += "3. Perform the analysis to answer the question\n"
    prompt += "4. Put user-facing tabular data in result['rows']; do not print DataFrames, Series, HTML tables, or the result JSON separately\n"
    prompt += "5. The sandbox computes data only. NEVER create, display, or save plots/images. For visualization requests, return chart-ready rows in result['datasets'] and declarative chart specs in result['visualizations']\n"
    prompt += "6. Make sure the code is complete and executable\n"
    prompt += "7. For statistical calculations (mean, median, sum, etc.), preserve the exact computed value\n"
    prompt += "8. ALWAYS finish by printing one structured result line in this exact format:\n"
    prompt += "   print('__DATASAYS_RESULT__' + json.dumps(result, ensure_ascii=False, default=str))\n"
    prompt += "9. The result dictionary MUST contain: answer_type, primary_value, unit, summary, rows, columns_used, metric_id, assumptions, insights, datasets, visualizations\n"
    prompt += "10. answer_type must be number, table, or text. rows must be a list of JSON objects. columns_used must contain exact CSV column names\n"
    prompt += "11. Import json. primary_value must be a Python int, float, str, bool, or null. For table answers set primary_value to null and put every record in rows\n\n"
    prompt += "12. metric_id MUST be one of plan.metric_ids from the grounded context. If plan.metric_ids is empty, metric_id MUST be null\n\n"
    prompt += "13. datasets is a list of {id, name, rows}; each id uses only letters, numbers, underscores, or hyphens. Each dataset contains at most 500 rows and all datasets together contain at most 2000 rows\n"
    prompt += "14. visualizations uses only: bar, line, pie, scatter, histogram, box, heatmap, table. Each item includes title and dataset_id\n"
    prompt += "15. bar/line/pie/scatter/histogram require x and y. heatmap requires x, y, value. box requires x, lower, q1, median, q3, upper. Referenced fields must exist in that dataset\n"
    prompt += "16. Compute histogram bins, box-plot five-number summaries, correlations, model coefficients, feature importance, and curve points in Python; return those values as rows instead of plotting them\n"
    prompt += "17. insights contains at most 5 concise evidence-grounded findings. Do not claim causality from correlation\n\n"
    prompt += "18. Write summary, insights, dataset names, visualization titles/descriptions, and user-facing row labels in the same language as the user's question\n\n"
    
    prompt += "## Important Notes:\n"
    if file_headers:
        # List all file IDs that will be available
        all_file_ids = [f['fileId'] for f in file_headers]
        prompt += f"- The following CSV files will be available in the current directory: {', '.join([f'{fid}.csv' for fid in all_file_ids])}\n"
        prompt += f"- Use the EXACT filename as shown above (e.g., '{file_headers[0]['fileId']}.csv')\n"
        prompt += f"- The CSV files are already in the current working directory, use relative paths like '{file_headers[0]['fileId']}.csv' (NOT absolute paths)\n"
        prompt += f"- DO NOT modify the filename - use it exactly as provided: '{file_headers[0]['fileId']}.csv'\n"
    prompt += "- The frontend renders result['rows']; avoid additional display prints that duplicate the result\n"
    prompt += "- The frontend renders approved visualizations interactively from datasets; words such as chart, dashboard, visualization, heatmap, histogram, or box plot are NOT permission to generate image code\n"
    prompt += "- Do NOT automatically drop rows or columns unless explicitly requested by the user\n"
    prompt += "- If the question asks about the raw data, use the data as-is without cleaning\n"
    prompt += "- Only clean or filter data if the user's question specifically requires it\n"
    prompt += "- Include comments for clarity\n"
    prompt += "- The code will be executed in a sandbox environment where the CSV files are in the current working directory\n"
    prompt += "- Use relative paths for CSV files (just the filename, e.g., 'file-id.csv'), NOT absolute paths\n"
    prompt += "- Include only a short reasoning summary before the code block; do not expose hidden chain-of-thought\n"
    prompt += "- Write the reasoning summary in the same language as the user's question\n"
    prompt += "- Put the Python code inside a markdown code block (```python ... ```)\n"
    prompt += "- The explanation helps users understand your approach\n\n"
    
    prompt += "Generate your response now (explanation + code):"
    
    return prompt


def _build_code_repair_prompt(
    question: str,
    file_headers: List[Dict[str, Any]],
    previous_code: str,
    execution_error: str,
    prompt_style: str,
    attempt_number: int,
    analysis_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Build prompt for repairing failed generated code."""
    prompt = "Repair the Python code below so it correctly answers the user's data analysis question.\n\n"
    prompt += f"## Repair Attempt\n{attempt_number}\n\n"
    prompt += "## Available CSV Files\n\n"

    for index, file in enumerate(file_headers, 1):
        file_id = file['fileId']
        prompt += f"### File {index}: {file['fileName']}\n"
        prompt += f"- File ID: {file_id}\n"
        prompt += f"- File Path: {file_id}.csv (use this exact relative filename)\n"
        prompt += f"- Columns: {', '.join(file['headers'])}\n"
        prompt += f"- Total Rows: {file['rows']}\n"
        prompt += f"- Total Columns: {file['columns']}\n\n"

    if analysis_context:
        prompt += "## Grounded Analysis Context\n"
        prompt += json.dumps(analysis_context, ensure_ascii=False, indent=2) + "\n\n"

    prompt += f"## User Question\n{question}\n\n"
    prompt += f"## Prompt Style Used\n{prompt_style}\n\n"
    prompt += "## Failed Code\n"
    prompt += f"```python\n{previous_code}\n```\n\n"
    prompt += "## Sandbox Error / Output\n"
    prompt += f"```\n{execution_error}\n```\n\n"
    prompt += "## Repair Requirements\n"
    prompt += "1. Return complete executable Python code only inside a markdown code block.\n"
    prompt += "2. Use pandas to read the CSV file with the exact relative filename shown above.\n"
    prompt += "3. Do not use absolute paths, network access, external files, shell commands, or interactive input.\n"
    prompt += "4. Preserve the user's analytical intent; fix only what is needed to make the code run and answer correctly.\n"
    prompt += "5. Put table records in result['rows']; do not print DataFrames, Series, or HTML tables.\n"
    prompt += "6. Remove all plotting and image code, including matplotlib, seaborn, plotly, PIL, and graphviz. Return chart-ready structured datasets and visualization specs even when the user explicitly asks for charts or a dashboard.\n\n"
    prompt += "7. ALWAYS emit a final __DATASAYS_RESULT__ JSON line with answer_type, primary_value, unit, summary, rows, columns_used, metric_id, assumptions, insights, datasets, and visualizations. For table answers, primary_value must be null.\n"
    prompt += "8. Use only metric IDs, columns, and definitions supplied in the grounded context.\n\n"
    prompt += "9. If the plan has no metric_ids, set result metric_id to null.\n\n"
    prompt += "10. Write the short repair summary in the same language as the user's question.\n\n"
    prompt += "11. Visualization types are restricted to bar, line, pie, scatter, histogram, box, heatmap, and table. Use the original result contract's required fields for each type.\n\n"
    prompt += "Generate the repaired code now:"
    return prompt
