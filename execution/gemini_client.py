import os


def generate_gemini_text(prompt, model_name=None, api_key=None):
    """Generate text through Google's current HTTP-based Gen AI SDK."""
    key = (api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise ValueError("Gemini API key is not configured.")

    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(
            timeout=60_000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    try:
        response = client.models.generate_content(
            model=(model_name or os.getenv("AI_ANALYST_GEMINI_MODEL") or "gemini-flash-latest").strip(),
            contents=prompt,
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text
    finally:
        client.close()
