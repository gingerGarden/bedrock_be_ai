from typing import Optional, Dict
from pydantic import BaseModel



# -----------------------------------------------------
# 요청 스키마 (User → 서버)
# -----------------------------------------------------
class ChatRequestType(BaseModel):
    """
    LLM 요청(Request) 데이터 구조.

    - 사용자가 LLM에게 질문을 전달할 때 사용하는 입력 포맷
    - txt / txt_dict 중 하나만 입력 가능

    Attributes:
        txt (str, optional): 단일 문자열 입력
            예) "오늘 날씨 어때?"
        txt_dict (dict, optional): 역할-콘텐츠 쌍 (대화 히스토리 입력)
            예) {
                    "system": "너는 친절한 AI야.",
                    "user": "안녕?"
                }
        model_name (str, optional): 사용할 모델명 (지정하지 않으면 기본 모델 사용)
        request_id (str, optional): 중단 요청 식별용 ID (FE의 타임스탬프(UUID))

    예시:
        {
            "txt": "서울 날씨 알려줘",
            "model_name": "gemma:2b-it"
        }
    """
    txt: Optional[str] = None
    txt_dict: Optional[Dict[str, str]] = None
    model_name: Optional[str] = None
    request_id: Optional[str] = None




# -----------------------------------------------------
# 응답 스키마 (서버 → User)
# -----------------------------------------------------
class RespMetaModelType(BaseModel):
    """
    모델 정보 메타데이터.
    
    Attributes:
        model (str): 사용된 모델명
        log (str): 모델 선택 과정에서 남긴 로그
    """
    model: str
    log: str

class RespMetaTokenType(BaseModel):
    """
    토큰 사용량 메타데이터.
    
    Attributes:
        input (int): 입력 토큰 수
        output (int): 출력 토큰 수
        total (int): 전체 토큰 수
    """
    input: int
    output: int
    total: int

class RespMetaSpentType(BaseModel):
    """
    처리 시간 메타데이터 (단위: ns).
    
    Attributes:
        total_ns (int): 전체 처리 소요 시간
        generate_ns (int): 실제 토큰 생성에 걸린 시간
    """
    total_ns: int
    generate_ns: int

class RespMetaType(BaseModel):
    """
    모델 실행 관련 메타데이터 전체 구조.
    
    Attributes:
        model (RespMetaModelType): 모델 정보
        token (RespMetaTokenType): 토큰 사용량
        spent (RespMetaSpentType): 처리 시간
    """
    model: RespMetaModelType
    token: RespMetaTokenType
    spent: RespMetaSpentType

class ChatResponseType(BaseModel):
    """
    LLM 응답(Response) 데이터 구조.

    Attributes:
        content (str): 모델이 생성한 텍스트
        metadata (RespMetaType): 모델 실행 관련 메타데이터
        done (bool): 응답 완료 여부 (스트리밍 시 마지막에 True)

    예시:
        {
            "content": "서울의 오늘 날씨는 맑습니다.",
            "metadata": {
                "model": {"model": "gemma:2b-it", "log": "[Model] True"},
                "token": {"input": 10, "output": 30, "total": 40},
                "spent": {"total_ns": 12345678, "generate_ns": 9876543}
            },
            "done": true
        }
    """
    content: str
    metadata: RespMetaType
    done: bool