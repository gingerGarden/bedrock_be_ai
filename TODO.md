# 1. Streaming 중 연결 종료 문제
* 현재 /web이나 /web_with_meta는 StreamingResponse를 이용해서 chunk 단위로 텍스트를 흘려보내죠.

* 만약 사용자가 브라우저를 닫거나 네트워크가 끊기면, 서버에서 generator(raw_resp)는 계속 돌 수 있어요.

* FastAPI의 StreamingResponse는 내부적으로 client disconnect 이벤트를 잡아주긴 하지만, 백엔드 LLM 클라이언트까지 "중단(cancel)" 신호를 전달하지 않을 수도 있습니다.

    * Ollama 같은 경우 ollama.generate(..., stream=True)에서 연결이 끊겨도 서버 입장에서는 계속 토큰을 생성할 수 있음.

    * 해결하려면 disconnect 체크를 해서 generator loop를 중간에 break해야 함.

<br>

# 2. 동시성 안전성 확인
* 지금 `AsyncChatBot`은 전역 객체 하나만 생성해서 모든 요청에서 공유합니다.

* 괜찮은 이유:

    * `AsyncChatBot.__call__()`은 매 요청마다 새로운 generator를 만들고,

    * 내부적으로 상태(shared state)를 저장하지 않아요.

* 따라서 race condition 가능성은 낮음.

* 다만, `ollama.AsyncClient` 같은 경우 내부 연결 풀(pool)이나 세션 객체를 재사용할 수 있으므로, 아주 많은 요청을 동시에 보낼 때 안정성을 한번 확인하는 게 좋아요. (부하 테스트 추천)

<br>

# 3. 초기 warm-up 문제
* LLM은 첫 호출 때 모델을 메모리에 로딩하거나 GPU 메모리에 올리는 과정 때문에 응답이 오래 걸려요.

* 예: 첫 요청 → 5~10초 걸림, 이후 요청 → 0.2초

* 실서비스에서는 사용자가 첫 요청에서 "느리다"는 인상을 받을 수 있죠.

* 그래서 서버 시작 시 더미 요청을 미리 보내서 모델을 메모리에 올려두는 걸 "warm-up"이라고 해요.