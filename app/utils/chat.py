import logging
import asyncio

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


logger = logging.getLogger(__name__)




class ChatResponse:
    """
    FastAPI와 KHA(LLM ChatBot)를 연결하는 핵심 유틸리티 클래스.

    주요 역할:
    1. 사용자의 요청(텍스트/딕셔너리)을 LLM이 이해할 수 있는 프롬프트로 변환.
    2. LLM의 응답(비스트리밍/스트리밍)을 FastAPI의 응답 규격(JSON/SSE)으로 변환.
    3. 예외 상황(백엔드 장애, 클라이언트 연결 끊김 등)에 대한 방어 로직 수행.
    """

    # -------------------------------------------------
    # 1. LLM 호출 엔진 (Entry Point)
    # -------------------------------------------------
    @staticmethod
    async def get(
            bot: AsyncChatBot,
            req: ChatRequestType,
            stream: bool
        ) -> RawResponse:
        """
        ChatBot으로부터 원시 응답(Raw Response)을 가져오는 진입점 메서드.

        [보안 및 안정성 강화 로직 포함]
        - LLM 백엔드(Ollama/vLLM 등) 호출 중 발생하는 예외를 캡처하여 시스템 중단을 방지함.
        - 에러 발생 시 사용자에게 친절한 에러 메시지를 제너레이터 또는 JSON 형태로 반환함.

        Args:
            bot: 전역 AsyncChatBot 인스턴스.
            req: 사용자 요청 객체 (텍스트, 모델명, 요청 ID 포함).
            stream: 스트리밍 모드 여부.

        Returns:
            RawResponse: 비스트리밍 시 Dict, 스트리밍 시 AsyncGenerator 객체 반환.
        """
        try:
            # 입력값 정규화 (프롬프트 스타일 적용)
            prompt = PromptStyle.get_prompt(
                txt=req.txt,
                txt_dict=req.txt_dict,
                style=CLIENT
            )
            # LLM 엔진 호출
            response = await bot(
                prompt=prompt,
                model_name=req.model_name,
                stream=stream
            )
            return response.raw_resp
        
        except Exception as e:
            # 장애 발생 시 로깅 및 방어 응답 생성 - 갑작스러운 이유로 대화 중단
            # TODO 로깅 추가 예정
            print(f"[Error] LLM 호출 중 예외 발생: {e}")

            if stream:
                # 스트리밍 모드 : 에러 메시지를 흘려보낼 제너레이터 반환
                async def error_gen(error_msg: str):
                    """
                    스트리밍 요청 중 에러 발생 시 호출되는 내부 비동기 제너레이터.
                    - 주의: 호출 시 await를 붙이지 않고 제너레이터 객체 자체를 return함.
                    """
                    yield {
                        ResponseKey.CONTENT: f"AI 모델 호출에 실패했습니다. (사유: {error_msg})", 
                        ResponseKey.DONE: True
                    }
                return error_gen(error_msg=str(e))
            else:
                # 일반 모드 : 에러 정보를 담은 딕셔너리 반환
                return {
                    ResponseKey.CONTENT: "AI 모델 서비스가 일시적으로 원활하지 않습니다.", 
                    "error_detail":str(e)
                }
    

    # -------------------------------------------------
    # 2. FastAPI용 StreamingResponse 팩토리
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
        LLM 원시 제너레이터를 FastAPI가 처리 가능한 StreamingResponse로 변환함.

        Args:
            raw_resp: LLM 엔진이 생성한 비동기 제너레이터.
            with_metadata: 응답 마지막에 실행 통계(토큰 수 등)를 포함할지 여부.
            request: FastAPI Request 객체 (연결 끊김 감지용).
            request_id: 중단 요청 추적용 고유 ID.
        """
        # 태스크 객체 저장 변수
        watcher_task = None

        # 1. 프로액티브 감시 태스크 (생명주기 관리 추가)
        # 백그라운드 태스크로 실행 (응답 생성과 병렬로 수행)
        if request and request_id:
            watcher_task = asyncio.create_task(
                cls._watch_disconnect(request, request_id)
            )

        # 2. 설정에 따른 제너레이터 선택 (텍스트만 or 메타데이터 포함)
        base_gen = (
            cls._generator_with_metadata_tail(raw_resp, request, request_id)
            if with_metadata else
            cls._generator_only_txt(raw_resp, request, request_id)
        )

        # 3. 라이프사이클 래퍼로 감싸서 반환
        return StreamingResponse(
            content=cls._lifecycle_wrapper(
                task=watcher_task, 
                gen=base_gen,
                request_id=request_id
            ),
            media_type="text/event-stream"
        )
    
    @classmethod
    async def _watch_disconnect(
            cls, 
            request: Request, 
            request_id: str
        ):
        try:
            while True:
                if await request.is_disconnected():
                    # 연결 끊김 감지 시 즉시 stop_signal에 추가
                    request.app.state.stop_signal.add(request_id)
                    # TODO - 로거 추후 연결
                    print(f"[Alert] Proactive disconnect detected: {request_id}")
                    break
                    
                await asyncio.sleep(0.5)    # 0.5초 간격으로 체크
        except asyncio.CancelledError:
            # 스트리밍이 정상 종료되어 감시 태스크가 취소될 때 호출됨
            pass
        except Exception as e:
            logger.error(f"Error in disconnect watcher: {e}")

    @classmethod
    async def _lifecycle_wrapper(
            cls, 
            task: None | asyncio.Task,  
            gen: AsyncGenerator, 
            request_id: str
        ):
        """
        제너레이터를 감싸서 끝날 때 태스크 취소
        """
        try:
            async for chunk in gen:
                yield chunk
        finally:
            # 스트리밍이 끝나면 감시 태스크도 확실히 종료 (자원 회수)
            if task and not task.done():
                task.cancel()   # 제너레이터 끝나면 감시자도 종료
                # TODO - 추후 로거 개발
                print(f"Disconnect watcher cancelled for {request_id}")


    # -------------------------------------------------
    # 3. 내부 Generator: 텍스트 스트림 최적화 모드
    # -------------------------------------------------
    @classmethod
    async def _generator_only_txt(
            cls,
            raw_resp: AsyncGenerator[Dict[str, Any], None],
            request: Request = None,
            request_id: str = None
        ) -> AsyncGenerator[str, None]:
        """
        LLM 응답에서 텍스트(Content)만 추출하여 SSE 포맷으로 변환 및 송출함.

        [자원 최적화 전략]
        1. 클라이언트 연결 끊김 감지: 브라우저 종료 시 즉시 루프를 탈출하여 GPU 연산을 중단시킴.
        2. 중단 신호(Stop Signal) 체크: 사용자 명시적 중단 요청 시 즉시 응답을 멈춤.
        3. 메모리 관리: finally 블록을 통해 중단 신호 저장소(state.stop_signal)를 청소함.

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
                
                # 중단 체크
                if await cls._should_stop(request, request_id):
                    break

                # SSE 규격으로 데이터 송출
                yield SSEConverter.str_to_sse(
                    txt=chunk.get(ResponseKey.CONTENT, "")
                )

        except Exception as e:
            # 생성 도중 예외 발생 시 클라이언트에 에러 노출
            # TODO - 추후 로거 연결 필요
            print(f"[Error] 스트리밍 생성 중 오류: {e}")
            yield SSEConverter.str_to_sse(txt=f"\n\n[오류 발생: {str(e)}]")

        finally:
            # [전략 3] 요청 완료/중단 후 시그널 제거 (메모리 누수 방지)
            # 루프가 정상 종료되든, 중단 신호로 break되든 discard하여 request_id 삭제(메모리 누수 방지)
            if request and request_id:
                request.app.state.stop_signal.discard(request_id)   # 신호 제거


    # -------------------------------------------------
    # 4. 내부 Generator: 텍스트 + 메타데이터 꼬리 모드
    # -------------------------------------------------
    @classmethod
    async def _generator_with_metadata_tail(
            cls,
            raw_resp: AsyncGenerator[Dict[str, Any], None],
            request: Request = None,
            request_id: str = None
        ) -> AsyncGenerator[str, None]:
        """
        텍스트를 스트리밍하고, 마지막 청크(DONE=True)에서 실행 정보를 포함하여 송출함.
        - 파라미터 및 자원 최적화 로직은 _generator_only_txt와 동일함.

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
                # 중단 체크
                if await cls._should_stop(request, request_id):
                    break
                
                # 청크 타입에 따른 SSE 이벤트 분기
                if chunk.get(ResponseKey.DONE, False):
                    # 마지막 정보(메타데이터)는 'done' 이벤트로 송출
                    yield SSEConverter.event_to_sse(event='done', data=chunk)
                else:
                    # 일반 텍스트 데이터 송출
                    yield SSEConverter.str_to_sse(txt=chunk.get(ResponseKey.CONTENT, ""))

        except Exception as e:
            # TODO 로거 연결 필요
            print(f"[Error] 스트리밍(메타) 생성 중 오류: {e}")
            yield SSEConverter.str_to_sse(txt=f"\n\n[시스템 오류: {str(e)}]")

        finally:
            # 요청 완료 후 시그널 제거
            if request and request_id:
                request.app.state.stop_signal.discard(request_id)


    @classmethod
    async def _should_stop(cls, request: Request, request_id: str) -> bool:

        if not request or not request_id:
            return False
        
        # [판단 1] 클라이언트 연결 끊김 (브라우저 닫기 등)
        if await request.is_disconnected():
            # TODO - 추후 로거 연결 필요 (logger.warning)
            print(f"[Info] Stop detected: Client connection lost. ID: {request_id}")
            return True
        
        # [판단 2] 사용자 명시적 중단 신호 (stop_signal 전송됨)
        if request_id in request.app.state.stop_signal:
            # TODO - 추후 로더 연결 필요 (logger.info)
            print(f"[Info] Stop detected: User interruption signal. ID: {request_id}")
            return True
        
        return False
