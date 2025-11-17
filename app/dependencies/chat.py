from fastapi import Request
from kha.chatbot import AsyncChatBot



def get_bot(request: Request) -> AsyncChatBot:
    """
    FastAPI 의존성 주입(Dependency Injection)에서 사용되는 헬퍼 함수.
    - app.state에 저장된 AsyncChatBot 인스턴스를 꺼내 반환한다.
    - 라우터 함수에서 Depends(get_bot)으로 선언하면,
      매 요청마다 동일한 전역 ChatBot 객체를 안전하게 주입받을 수 있다.

    Args:
        request (Request): FastAPI Request 객체
            - app.state를 통해 전역으로 공유된 bot 인스턴스에 접근 가능

    Returns:
        AsyncChatBot: 현재 실행 중인 LLM 백엔드 클라이언트
    """
    return request.app.state.bot


