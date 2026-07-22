from fastapi import APIRouter

from app.api.v1.chat import chat_router, retrieval_router
from app.api.v1.documents import router as documents_router
from app.api.v1.evaluation import router as evaluation_router
from app.api.v1.ingestion_jobs import router as ingestion_jobs_router
from app.api.v1.system import router as system_router
from app.api.v1.uploads import router as uploads_router

router = APIRouter(prefix="/api/v1")
router.include_router(system_router)
router.include_router(uploads_router)
router.include_router(documents_router)
router.include_router(ingestion_jobs_router)
router.include_router(chat_router)
router.include_router(retrieval_router)
router.include_router(evaluation_router)
