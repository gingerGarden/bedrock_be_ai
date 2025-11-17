# 서버간 연결 구조
* 서버 A: 프론트엔드 웹서버
> * Alpha: Streamlit
> * Beta: React
* 서버 B: 백엔드 웹서버
> * FastAPI

<br>
<br>
<br>
<br>

# A. 정식 연결 - 온프레미스 내부망을 통한 연결

### 1. 서버 B (백엔드) 실행
> * 외부에서는 접근 못하게 함
> * 서버 A에서만 접근 가능하게 하려는 경우, 서버 B의 내부망 IP에 바인딩

```bash
# 서버 B의 내부 IP가 192.168.0.20 인 경우
uvicorn main:app --host 192.168.0.20 --port 8000

# reload 인자 주는 경우
uvicorn main:app --reload --host 192.168.0.20 --port 8000
```
* 이 경우, `localhost`는 물론이고, 같은 내부망에 있는 다른 서버에서도 접근 가능

<br>
<br>

### 2. 서버 B 방화벽 설정 (ufw 예시)
* 서버 A의 내부 IP가 `192.168.0.10`이라 가정

```bash
# 서버 B 방화벽에서 A만 허용
sudo ufw allow from 192.168.0.10 to any port 8000

# 다른 외부 접근은 차단
sudo ufw deny 8000
```
* 이 경우 서버 A는 `http://192.168.0.20:8000` 으로 접속 가능
> * 외부 유저가 직접 192.168.0.20:8000으로는 접근 불가.

<br>
<br>

### 3. 서버 A (프론트엔드) 설정
* 프론트엔드에서 API 요청할 때 서버 B의 내부망 IP 지정

```python
# Server A 프론트엔드 코드
BACKEND_URL = "http://192.168.0.20:8000"

# 예: FastAPI에서 프록시 호출
import requests
resp = requests.get(f"{BACKEND_URL}/api_chat")
```

* 외부 유저는 서버 A에만 접근
> * 서버 A는 내부망을 통해 서버 B API 호출 > 응답 전달

<br>
<br>

### 4. 최종 구조
```scss
[ User ] → (HTTP/HTTPS, 공개)
      └──> Server A (Frontend Web Server, Public)
                │
                ▼
         (온프레미스 내부망, IP 제한)
                │
                ▼
           Server B (Backend API, Private)
```

<br>

#### 디렉터리 구조
```text
kha_backend/
│
├── .env
├── .gitignore
├── main.py
├── README.md
├── requirements.txt
├── TESTBED.ipynb
│
└── app/
    ├── core/
    │   ├── __init__.py
    │   └── config.py
    │
    ├── dependencies/
    │   ├── __init__.py
    │   └── chat.py
    │
    ├── routes/
    │   └── v0/
    │       ├── __init__.py
    │       ├── base.py
    │       └── chat.py
    │
    ├── schemas/
    │   ├── __init__.py
    │   └── chat.py
    │
    └── utils/
        ├── __init__.py
        └── chat.py
```

<br>
<br>
<br>
<br>

## B. 개발 단계 연결

* 백엔드 localhost 연결

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8030
```

<br>

* 서버 A -> 서버 B 터널링
> * 서버 A에서 `http://localhost:8000` 요청 시, 자동으로 서버 B의 FastAPI로 연결
> * 프론트엔드 개발 시, "백엔드가 동일 머신에 있는 것처럼" 사용 가능
* wsl 환경이므로, 윈도우 PowerShell에서 실행 후, IP를 윈도우로 할 것
> * 윈도우와 wsl의 IP가 상이함
```bash
ssh -L 8000:localhost:8000 user@serverB
```

* 여전히 wsl로 localhost를 쓰고 싶다면
> * 우분투는 윈도우랑 다르게 핑을 계속 보내지 않으므로 자동으로 끊어짐
> * 아래처럼 60초마다 최대 5번까지 신호를 자동으로 보내게 셋팅
```bash
ssh -fN -o ServerAliveInterval=60 -o ServerAliveCountMax=5 -L 8030:localhost:8030 user@serverB
```
> * `-fN`: 백그라운드
> * `-o ServerAliveInterval=60` : 60초 간격 신호 전달
> * `-o ServerAliveCountMax=5` : 최대 5회
