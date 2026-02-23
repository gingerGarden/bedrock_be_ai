from typing import Dict, Any, AsyncGenerator

from fastapi.responses import StreamingResponse
from fastapi import Request

from app.core.config import CLIENT
from app.schemas.chat import ChatRequestType

from bedrock_core.data.sse import SSEConverter

from kha.chatbot import AsyncChatBot
from kha.prompt.style import PromptStyle
from kha.schema.keys import ResponseKey 
from kha.schema.types import RawResponse




class ChatResponse:
    """
    FastAPI ↔ KHA(ChatBot) 연결 유틸리티 클래스.

    역할:
    - FastAPI 엔드포인트에서 받은 요청을 KHA AsyncChatBot에 전달하고,
      응답을 FastAPI가 처리할 수 있는 포맷(JSON or SSE stream)으로 변환한다.
    - 스트리밍 / 비스트리밍 응답 모두 지원.
    - SSE(Server-Sent Events) 형식으로 변환하여 실시간 전송 가능.

    사용 시나리오:
    - /api → 비스트리밍 (JSON 1회 반환)
    - /web → 스트리밍 (텍스트만 반환)
    - /web_with_meta → 스트리밍 (텍스트 + 마지막에 메타데이터 반환)
    """

    # -------------------------------------------------
    # 1. LLM 호출 (Non-stream / Stream 공통)
    # -------------------------------------------------
    @staticmethod
    async def get(
            bot: AsyncChatBot,
            req: ChatRequestType,
            stream: bool
        ) -> RawResponse:
        """
        ChatBot으로부터 원시 응답(raw_resp)을 가져온다.

        처리 과정:
        1. PromptStyle.get_prompt() → txt / txt_dict 입력을 정규화
        2. bot(...) 호출 → AsyncChatBot 실행
        3. raw_resp 반환 → dict(비스트리밍) 또는 generator(스트리밍)

        Args:
            bot (AsyncChatBot): 전역으로 공유된 ChatBot 객체
            req (ChatRequestType): 사용자 요청 (txt / txt_dict / model_name)
            stream (bool): 스트리밍 여부
                - False → dict 반환
                - True  → AsyncGenerator 반환

        Returns:
            RawResponse:
                - Non-stream → Dict[str, Any]
                - Stream → AsyncGenerator[Dict[str, Any], None]
        """
        # 프롬프트 표준화 (txt / txt_dict → 통합 포맷)
        prompt = PromptStyle.get_prompt(
            txt=req.txt,
            txt_dict=req.txt_dict,
            style=CLIENT
        )
        # LLM 호출
        response = await bot(
            prompt=prompt,
            model_name=req.model_name,
            stream=stream
        )
        return response.raw_resp
    

    # -------------------------------------------------
    # 2. StreamingResponse 생성
    # -------------------------------------------------
    @classmethod
    def streaming(
            cls,
            raw_resp: AsyncGenerator[Dict[str, Any], None],
            with_metadata: bool = False,
            request: Request = None,
            request_id: str = None
        ) -> StreamingResponse:
        """
        LLM 응답(raw_resp)을 FastAPI StreamingResponse로 변환한다.

        Args:
            raw_resp (AsyncGenerator[Dict[str, Any], None]):
                LLM이 생성한 스트리밍 응답 제너레이터
            with_metadata (bool, optional):
                마지막 응답 시 메타데이터를 포함할지 여부. 기본 False.
                - False → content만 전송 (성능 최적화)
                - True  → 마지막 chunk에서 {"done": true, "metadata": {...}} 직렬화 전송
            request (Request, optional):
                FastAPI Request 객체 (전역 상태 접근용)
            request_id (str, optional):
                중단 요청 식별용 ID

        Returns:
            StreamingResponse: text/event-stream
                클라이언트와 SSE(Server-Sent Events) 방식으로 통신 가능
        """
        # choose generator
        if with_metadata:
            generator = cls._generator_with_metadata_tail(
                raw_resp, request, request_id
            )
        else:
            generator = cls._generator_only_txt(
                raw_resp, request, request_id
            )
        
        return StreamingResponse(
            content=generator,
            media_type="text/event-stream"
        )
    

    # -------------------------------------------------
    # 3. 내부 generator: content만 전송
    # -------------------------------------------------
    @classmethod
    async def _generator_only_txt(
            cls,
            raw_resp: AsyncGenerator[Dict[str, Any], None],
            request: Request = None,
            request_id: str = None
        ) -> AsyncGenerator[str, None]:
        """
        스트리밍 제너레이터 (텍스트만 전송).
        - 코루틴을 반환해야하므로, streaming()에서 해당 메서드 앞엔 await가 붙지 않음

        Args:
            raw_resp (AsyncGenerator[Dict[str, Any], None]):
                LLM이 생성한 스트리밍 응답 (dict 형태)
            request (Request, optional):
                FastAPI Request 객체
            request_id (str, optional):
                중단 요청 식별용 ID

        Yields:
            str: SSE 포맷으로 변환된 content 문자열

        예시 응답:
            data: 오늘 날씨는
            \n\n
            data: 맑고 화창합니다.
            \n\n
        """

        # 중단 방식
        """
        출력 소비(consume)를 중단 시키는 방식
        - 제너레이터 루프를 break하여 asyncio 환경에서 해당 요청을 담당하던 비동기 작업 종료
        - 이때 kha 패키지와의 연결도 같이 닫히며, 서버측에서도 해당 스트리밍 요청에 대한 연산 중단
        
        - 해당 방식은 LLM 연산 자체를 kill하는 것이 아님
            > LLM 내부에서는 이미 다음 토큰을 계산 중일 수 있음
            > 그러나 결과를 더 이상 yield 하지 않음
            > 클라이언트로 전송되지 않음
            > 스트림 연결 닫힘
        - 만약 LLM task를 강제 cancel하면 오히려 리소스/락 문제가 생길 수 있음
        """
        try:
            async for chunk in raw_resp:
                # 중단 신호 체크
                if request and request_id:
                    if request_id in request.app.state.stop_signal:
                        # 여기서 break를 하면 finally로 이동함
                        break
                yield SSEConverter.str_to_sse(
                    txt=chunk.get(ResponseKey.CONTENT, "")
                )
        finally:
            # 루프가 정상 종료되든, 중단 신호로 break되든 discard하여 request_id 삭제(메모리 누수 방지)
            if request and request_id:
                request.app.state.stop_signal.discard(request_id)   # 신호 제거


    # -------------------------------------------------
    # 4. 내부 generator: content + 마지막에 metadata 전송
    # -------------------------------------------------
    @classmethod
    async def _generator_with_metadata_tail(
            cls,
            raw_resp: AsyncGenerator[Dict[str, Any], None],
            request: Request = None,
            request_id: str = None
        ) -> AsyncGenerator[str, None]:
        """
        스트리밍 제너레이터 (텍스트 + 마지막에 메타데이터 전송).
        - 코루틴을 반환해야하므로, streaming()에서 해당 메서드 앞엔 await가 붙지 않음

        Args:
            raw_resp (AsyncGenerator[Dict[str, Any], None]):
                LLM이 생성한 스트리밍 응답 (dict 형태)
            request (Request, optional):
                FastAPI Request 객체
            request_id (str, optional):
                중단 요청 식별용 ID

        Yields:
            str:
                - 일반 chunk → content 문자열
                - 마지막 chunk (DONE=True) → metadata JSON 직렬화 + "done" 이벤트

        예시 응답:
            data: 오늘 날씨는
            \n\n
            data: 맑고 화창합니다.
            \n\n
            event: done
            data: {
                "done": true,
                "metadata": {...}
            }
            \n\n
        """
        try:
            async for chunk in raw_resp:
                # 중단 신호 체크 로직
                if request and request_id:
                    if request_id in request.app.state.stop_signal:
                        break
            if chunk.get(ResponseKey.DONE, False):
                yield SSEConverter.event_to_sse(
                    event='done', data=chunk
                )
            else:
                yield SSEConverter.str_to_sse(
                    txt=chunk.get(ResponseKey.CONTENT, "")
                )
        finally:
            # 응답 완료 후 반드시 신호 제거
            if request and request_id:
                request.app.state.stop_signal.discard(request_id)