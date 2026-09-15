# 2:17 AM — Music → Visual Generator

MVP Streamlit app for the 2:17 AM TikTok workflow.

Flow:
1. Upload reference video
2. Extract audio only
3. Send audio to Gemini
4. Generate music analysis, visual concept, English image prompt, and short Vietnamese caption
5. Download result as TXT

## Streamlit Secrets

Add:

```toml
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
APP_PASSWORD = "YOUR_PRIVATE_APP_PASSWORD"
```

Do not commit `secrets.toml`.

## Deploy

Deploy `app.py` on Streamlit Community Cloud and paste the two secrets in Advanced settings.
