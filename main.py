from fastapi import FastAPI

from app.core.config import CLIENT
from app.routes.v0 import chat, base

from kha.chatbot import AsyncChatBot



# -----------------------------------------------------
# 1. 전역 LLM Client 초기화
# -----------------------------------------------------
# - 앱 실행 시 단 한 번만 AsyncChatBot을 생성
# - backend 인자는 CLIENT (환경설정에서 지정, 예: "ollama", "vllm")
# - app.state에 저장해두고 의존성 주입(Depends)으로 각 API에서 재사용
bot = AsyncChatBot(backend=CLIENT)       # LLM Client



# -----------------------------------------------------
# 2. FastAPI 앱 인스턴스 생성
# -----------------------------------------------------
# - 모든 엔드포인트(router)는 이 app 객체에 등록됨
# - app.state에 bot 객체를 붙여서 전역 공유 가능
app = FastAPI()

# app의 전역 공유 객체
app.state.bot = bot     # bot 객체



# -----------------------------------------------------
# 3. Router 등록
# -----------------------------------------------------
# - 라우터 단위로 기능을 모듈화
# - base: 서버 상태 확인, 헬스체크 (예: /ping)
# - chat: LLM API (비스트리밍 / 스트리밍)

# - prefix: 버전(v0) 및 기능별 경로
# - tags: 자동 문서화(swagger UI)에서 그룹핑 용도

# router 연결
app.include_router(
    router=base.router,
    prefix="/v0/base",
    tags=["base"],
    dependencies=[]
)
app.include_router(
    router=chat.router, 
    prefix="/v0/chat", 
    tags=["chat"], 
    dependencies=[]
)