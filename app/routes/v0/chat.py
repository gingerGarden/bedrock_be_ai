from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequestType, ChatResponseType
from app.dependencies.chat import get_bot
from app.utils.chat import ChatResponse

from kha.chatbot import AsyncChatBot



# -----------------------------------------------------
# Chat Router
# - LLM 호출 관련 API 모음
# - prefix: /v0/chat
# -----------------------------------------------------
router = APIRouter()



# -----------------------------------------------------
# 1. Non-streaming API (JSON 응답 1회 반환)
# -----------------------------------------------------
@router.post(
    "/api", 
    response_model=ChatResponseType,
    summary="API용 Response 단일 전달 (메타데이터 포함)",
    description="LLM 응답 전체를 JSON으로 1회 반환 (content, metadata, done)"
)
async def api_chat(
        req: ChatRequestType, 
        bot: AsyncChatBot = Depends(get_bot)
    ) -> ChatResponseType:
    """
    일반 API 호출용 엔드포인트 (비스트리밍 모드).
    
    - 요청: ChatRequestType
        * txt (str, optional): 단일 텍스트 입력
        * txt_dict (dict, optional): 역할-콘텐츠 dict 입력
        * model_name (str, optional): 사용할 LLM 모델명
    - 응답: ChatResponseType
        * content (str): 모델이 생성한 전체 응답 텍스트
        * metadata (dict): 모델명/토큰 수/소요시간 등 실행 정보
        * done (bool): 응답 완료 여부 (항상 True)
    - 사용 예시: 
        * 배치 처리 (한 번에 JSON 결과 필요)
        * API 호출 기반 inference (동기 호출)

    Args:
        req (ChatRequestType): LLM 요청 객체
        bot (AsyncChatBot, optional): LLM Bot 객체. Defaults to Depends(get_bot).

    Returns:
        ChatResponseType: content / metadata / done
            - metadata 예시:
                {
                    "model": {"name": "gemma:2b-it"},
                    "token": {"input": 128, "output": 512},
                    "spent": {"sec": 0.231}
                }
    """
    # 응답 반환 - json
    return await ChatResponse.get(bot=bot, req=req, stream=False)



# -----------------------------------------------------
# 2. Streaming API (텍스트만 전달)
# -----------------------------------------------------
@router.post(
    "/web",
    responses={200: {"content": {"text/event-stream": {}}}},
    summary="실시간 스트리밍 (content만 전달)",
    description="텍스트 chunk 단위로 스트리밍 전송. 성능 최적화된 기본 모드."
)
async def web_chat(
        req: ChatRequestType,
        request: Request,   # 전역 상태 접근용
        bot: AsyncChatBot = Depends(get_bot)
    ) -> StreamingResponse:
    """
    실시간 스트리밍 API (텍스트만 반환).
    
    - 요청: ChatRequestType (txt / txt_dict / model_name)
    - 응답: text/event-stream
        * 각 chunk마다 `content` 텍스트만 전달
        * 마지막 chunk에는 metadata 없음 (성능 최적화)
    - 사용 예시:
        * 실시간 채팅 UI
        * "타자치는 듯한" 점차 출력 효과

    Args:
        req (ChatRequestType): LLM 요청 객체
        request (Request): FastAPI Request 객체 (전역 상태 접근용)
        bot (AsyncChatBot, optional): LLM Bot 객체. Defaults to Depends(get_bot).

    Returns:
        StreamingResponse: text/event-stream
            - yield 예시:
                data: 오늘 날씨는
                \n\n
                data: 맑고 화창합니다.
                \n\n
                ...
    """
    # Response 생성
    raw_resp = await ChatResponse.get(bot=bot, req=req, stream=True)
    # streaming 출력 - streaming 메서드에 request와 request_id 전달
    return ChatResponse.streaming(
        raw_resp, 
        with_metadata=False,
        request=request,
        request_id=req.request_id
    )



# -----------------------------------------------------
# 3. Streaming API (텍스트 + 마지막에 metadata 포함)
# -----------------------------------------------------
@router.post(
    "/web_with_meta",
    responses={200: {"content": {"text/event-stream": {}}}},
    summary="실시간 스트리밍 (메타데이터 포함)",
    description="텍스트는 chunk 단위로, 마지막에는 실행 메타데이터까지 JSON 직렬화 전송."
)
async def web_chat_with_metadata(
        req: ChatRequestType,
        request: Request,
        bot: AsyncChatBot = Depends(get_bot)
    ) -> StreamingResponse:
    """
    실시간 스트리밍 API (텍스트 + 마지막에 metadata 포함).
    
    - 요청: ChatRequestType (txt / txt_dict / model_name)
    - 응답: text/event-stream
        * 일반 chunk → content 텍스트
        * 마지막 chunk → {"done": true, "metadata": {...}} JSON 직렬화
    - 사용 예시:
        * 프론트엔드에서 실시간 텍스트 + 마지막에 모델 실행 결과(토큰 수, 시간 등)까지 필요할 때

    Args:
        req (ChatRequestType): LLM 요청 객체
        request (Request): FastAPI Request 객체 (전역 상태 접근용)
        bot (AsyncChatBot, optional): LLM Bot 객체. Defaults to Depends(get_bot).

    Returns:
        StreamingResponse: text/event-stream
            - yield 예시:
                data: 오늘 날씨는
                \n\n
                data: 맑고 화창합니다.
                \n\n
                ...
                event: done
                data: {
                    "done": true,
                    "metadata": {
                        "model": {"name": "gemma:2b-it", "log": "[Model] True"},
                        "token": {"input": 12, "output": 34, "total": 46},
                        "spent": {"total_ns": 12345678, "generate_ns": 9876543}
                    }
                }
                \n\n
    """
    # Response 생성
    raw_resp = await ChatResponse.get(bot=bot, req=req, stream=True)
    # streaming 출력
    return ChatResponse.streaming(
        raw_resp, 
        with_metadata=True,
        request=request,
        request_id=req.request_id
    )



# -----------------------------------------------------
# 4. Streaming 중단 요청 처리 API
# >>> web_chat, web_chat_with_metadata 정지
# -----------------------------------------------------
@router.post("/stop_streaming")
async def stop_generation(
        req: ChatRequestType, 
        request: Request
    ):
    """
    작업 중단 로직:
    - stop_signal(set)에 request_id를 등록
    - streaming generator 루프에서 이를 감지하여 break 수행

    Test:
        1) 스트리밍 시작:
           curl -N -X POST http://localhost:8030/v0/chat/web -H "Content-Type: application/json" -d '{"txt": "1부터 100까지 숫자를 세며 아주 긴 이야기해줘", "txt_dict": null, "model_name": "gemma:2b", "request_id": "test_stop_123"}'
        2) 즉시 중단:
           curl -X POST http://localhost:8030/v0/chat/stop_streaming -H "Content-Type: application/json" -d '{ "txt": null, "txt_dict": null, "model_name": null, "request_id": "test_stop_123"}'
    """
    if req.request_id:
        request.app.state.stop_signal.add(req.request_id)
    return {"ok":True}
