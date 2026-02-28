from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.core.logging_config import configure_logging, get_logger

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=ROOT_DIR / ".env")
configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="MolduBot API", version="0.1.0")

# Outlook WebView and ngrok environments can vary by origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
logger.info("FastAPI 라우터 등록 완료")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    logger.debug("루트 경로 접속: taskpane로 리다이렉트")
    return RedirectResponse(url="/addin/taskpane.html")


# Static routes used by manifest + taskpane fallback links.
app.mount(
    "/addin",
    StaticFiles(directory=ROOT_DIR / "clients" / "outlook-addin", html=True),
    name="addin",
)
app.mount(
    "/myhr",
    StaticFiles(directory=ROOT_DIR / "clients" / "portals" / "myHR", html=True),
    name="myhr",
)
app.mount(
    "/myPromise",
    StaticFiles(directory=ROOT_DIR / "clients" / "portals" / "myPromise", html=True),
    name="myPromise",
)
app.mount(
    "/promise",
    StaticFiles(directory=ROOT_DIR / "clients" / "portals" / "myPromise", html=True),
    name="promise",
)
app.mount(
    "/finance",
    StaticFiles(directory=ROOT_DIR / "clients" / "portals" / "finance", html=True),
    name="finance",
)
