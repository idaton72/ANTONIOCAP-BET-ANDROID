ANTONIOCAP.BET ANDROID 0.4 — 3.8.6 + BETSHOOT

STATO
- Motore originale ANTONIOCAP.BET 3.8.6 preservato lato server.
- Android visualizza TOP 50 e stato fonti via /api/top50.
- Betshoot Dropping Odds aggiunto come fonte pubblica, con segnali distinti 1/X/2, Over 2.5, Under 2.5 e BTTS.
- Betshoot non bypassa login/paywall: usa esclusivamente righe pubbliche.
- Fonti Playwright restano lato server per compatibilita' con Chromium.

BUILD SENZA ANDROID STUDIO
1. Caricare la cartella android in un repository GitHub.
2. Aprire Actions > Build ANTONIOCAP.BET APK > Run workflow.
3. Scaricare l'artifact APK prodotto dalla action.

SERVER
cd server
pip install -r requirements.txt
playwright install chromium
python -m uvicorn app:app --host 0.0.0.0 --port 8765

NOTA
L'APK e' il client Android; il motore completo 3.8.6 resta un servizio perché Playwright/Chromium desktop non e' eseguibile nativamente dentro un normale APK Android.
