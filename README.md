# Aether AI — full starter

FastAPI + MongoDB Atlas + Groq chat + Cloudflare image generation + Cesium globe + OpenWeather + GitHub analysis/write preview.

## Deploy
1. Upload the contents of this archive to your GitHub repository (replace matching starter files).
2. In Render, create/update the web service using `render.yaml` or set build `pip install -r requirements.txt` and start `uvicorn main:app --host 0.0.0.0 --port $PORT`.
3. Add environment variables from `.env.example` in Render. Never commit real keys. `MONGODB_URI` and `SECRET_KEY` are required for accounts.
4. Create a Cesium ion access token for globe terrain/imagery. Add Groq, Cloudflare, OpenWeather and GitHub tokens to enable those services.
5. Test `/api/health`, register, sign in, send a chat prompt, and open the Earth workspace.

## Features
- Secure password hashing and signed HttpOnly session cookie; MongoDB-backed account and chat history.
- Groq chat with recent conversational context.
- Voice recognition and speech synthesis in supported browsers (microphone permission required).
- Cesium 3D globe with terrain, satellite/normal imagery, and weather overlay controls. Cesium imagery/terrain availability depends on token permissions and provider quotas.
- OpenWeather current conditions and short forecast for a searched place. Weather map tiles depend on the API plan and may not be enabled for every account.
- Cloudflare Workers AI image generation; generated files are returned to the browser.
- GitHub public/private repository structure analysis; optional code generation; proposed file changes require a separate explicit confirmation before GitHub writes. Use a least-privilege token.

## Notes
This is an integrated starter, not a claim that all third-party APIs are activated automatically. Provider accounts, permissions, quotas and keys are required. The browser globe uses CDN-hosted CesiumJS and requires network access.
