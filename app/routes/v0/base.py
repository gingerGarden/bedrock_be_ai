from typing import Dict, List
from fastapi import APIRouter, Depends
from app.dependencies.chat import get_bot
from kha.chatbot import AsyncChatBot



# -----------------------------------------------------
# Base Router
# - 서버 상태 확인용 엔드포인트 모음
# - prefix: /v0/base
# -----------------------------------------------------
router = APIRouter()



@router.get(
    "/ping", 
    response_model=Dict[str, str],
    summary="백엔드 웹서버 상태 확인",
    description="연결 상태와 현재 백엔드 클라이언트 이름 반환"
)
async def ping(
        bot: AsyncChatBot = Depends(get_bot)
    ) -> Dict[str, str]:
    """
    서버 상태 확인(Health Check) 엔드포인트.

    - 주로 로드밸런서, 모니터링 시스템, 운영자가
      "서버가 정상적으로 응답 가능한 상태인지" 확인할 때 사용한다.
    - bot 의존성을 주입받아, 현재 연결된 LLM backend 이름까지 함께 반환한다.

    Args:
        bot (AsyncChatBot): get_bot()을 통해 주입된 전역 ChatBot 객체

    Returns:
        dict:
            {
                "status": "good",         # 서버 응답 상태
                "bot_backend": "ollama"   # 현재 사용 중인 백엔드 이름
            }
    """
    return {
        "status":"good", 
        "bot_backend":bot.backend_name
    }


@router.get(
    "/model_list", 
    response_model=List[str],
    summary="백엔드 클라이언트에서 사용 가능한 모델명 반환",
    description="현재 사용 가능한 모델명을 리스트로 반환"
)
async def get_models(
        bot: AsyncChatBot = Depends(get_bot)
    ) -> List[str]:
    """
    현재 클라이언트가 사용 가능한 모델 리스트 반환

    Args:
        bot (AsyncChatBot, optional): get_bot()을 통해 주입된 전역 ChatBot 객체

    Returns:
        List[str]: 사용 가능한 모델 이름의 리스트
            예) ["gemma:2b", "gemma:7b"]
    """
    return bot.model_list


@router.get(
    "/default_model",
    response_model=str,
    summary="백엔드 클라이언트의 디폴트 모델명 반환",
    description="현재 백엔드 클라이언트에서 디폴트로 잡혀있는 모델명 반환"
)
async def default_model(
        bot: AsyncChatBot = Depends(get_bot)
    ) -> str:
    """
    현재 클라이언트의 디폴트 모델 반환

    Args:
        bot (AsyncChatBot, optional): get_bot()을 통해 주입된 전역 ChatBot 객체

    Returns:
        str: 현재 Client에 설정된 모델명
    """
    return bot.default_model