# SRTgo: K-Train (KTX, SRT) Reservation Assistant
[![Upload Python Package](https://github.com/lapis42/srtgo/actions/workflows/python-publish.yml/badge.svg)](https://github.com/lapis42/srtgo/actions/workflows/python-publish.yml)
[![Downloads](https://static.pepy.tech/badge/srtgo)](https://pepy.tech/project/srtgo)
[![Downloads](https://static.pepy.tech/badge/srtgo/month)](https://pepy.tech/project/srtgo)
[![Python version](https://img.shields.io/pypi/pyversions/srtgo)](https://pypistats.org/packages/srtgo)

> [!WARNING]  
> 본 프로그램의 모든 상업적, 영리적 이용을 엄격히 금지합니다. 본 프로그램 사용에 따른 민형사상 책임을 포함한 모든 책임은 사용자에게 따르며, 본 프로그램의 개발자는 민형사상 책임을 포함한 어떠한 책임도 부담하지 아니합니다. 본 프로그램을 내려받음으로써 모든 사용자는 위 사항에 아무런 이의 없이 동의하는 것으로 간주됩니다.

> [!IMPORTANT]
> 본 프로그램에 입력하는 아이디, 비번, 카드번호, 예매 설정 등은 로컬 컴퓨터에 [keyring 모듈](https://pypi.org/project/keyring/)을 통하여 저장하며 그 이외의 위치에 네트워크 전송 등을 통하여 공유되지 않습니다.

## 주요 기능
- SRT 및 KTX 기차표 자동 예매
- 텔레그램 알림 전송
  - [Bot Token 및 Chat ID 얻기](https://gabrielkim.tistory.com/entry/Telegram-Bot-Token-%EB%B0%8F-Chat-Id-%EC%96%BB%EA%B8%B0)
- 자동 신용카드 결제
- 자주 사용하는 역 설정
- 어린이/우대 예매 지원
- 매진 시 예약대기 신청

---
> [!WARNING]
> All commercial and commercial use of this program is strictly prohibited. Use of this program is at your own risk, and the developers of this program shall not be liable for any liability, including civil or criminal liability. By downloading this program, all users agree to the above without any objection.

> [!IMPORTANT]  
> All sensitive data (login, payment info, settings) is stored locally via [keyring](https://pypi.org/project/keyring/) and never transmitted.

## Key Features
- Automated SRT/KTX ticket reservations
- Telegram notifications
- Automatic credit card payment
- Favorite station presets  
- Child/Senior ticket support
- Waitlist for sold-out trains

## Installation / Update
```bash
pip install srtgo -U
```

- Install beta version (can be unstable)
```bash
pip install git+https://github.com/lapis42/srtgo -U
```

## Using SRTgo

```bash
> srtgo
```

```bash
[?] 메뉴 선택 (↕:이동, Enter: 선택): 예매 시작
 > 예매 시작
   예매 확인/취소
   로그인 설정
   텔레그램 설정
   카드 설정
   역 설정
   역 직접 수정
   예매 옵션 설정
   나가기

[?] 열차 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소): SRT
 > SRT
   KTX
   취소

[?] 출발역 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소): 수서
 > 수서
   대전
   동대구
   부산

[?] 도착역 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소): 동대구
   수서
   대전
 > 동대구
   부산

[?] 출발 날짜 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소): 2024/01/04 Thu
   2024/01/03 Wed
 > 2024/01/04 Thu
   2024/01/05 Fri
   2024/01/06 Sat
   2024/01/07 Sun
   2024/01/08 Mon
   2024/01/09 Tue
   2024/01/10 Wed
   2024/01/11 Thu
   2024/01/12 Fri
   2024/01/13 Sat
   2024/01/14 Sun
   2024/01/15 Mon

[?] 출발 시각 선택 (↕:이동, Enter: 완료, Ctrl-C: 취소): 10
   00
   02
   04
   06
   08
 > 10
   12
   14
   16
   18
   20
   22

[?] 승객수 (↕:이동, Enter: 완료, Ctrl-C: 취소): 1
 > 1
   2
   3
   4
   5
   6
   7
   8
   9

[?] 예약할 열차 선택 (↕:이동, Space: 선택, Enter: 완료, Ctrl-C: 취소): 
   [ ] [SRT 323] 01월 04일, 수서~동대구(10:00~11:40) 특실 매진, 일반실 매진, 예약대기 불가능
   [ ] [SRT 325] 01월 04일, 수서~동대구(10:30~12:17) 특실 매진, 일반실 매진, 예약대기 불가능
   [ ] [SRT 327] 01월 04일, 수서~동대구(10:50~12:30) 특실 매진, 일반실 매진, 예약대기 불가능
   [ ] [SRT 381] 01월 04일, 수서~동대구(12:04~13:55) 특실 매진, 일반실 매진, 예약대기 불가능
   [ ] [SRT 331] 01월 04일, 수서~동대구(12:28~14:08) 특실 매진, 일반실 매진, 예약대기 불가능
 > [ ] [SRT 333] 01월 04일, 수서~동대구(12:50~14:34) 특실 매진, 일반실 매진, 예약대기 불가능
   [X] [SRT 335] 01월 04일, 수서~동대구(13:00~14:46) 특실 매진, 일반실 예약가능, 예약대기 불가능
   [ ] [SRT 337] 01월 04일, 수서~동대구(13:30~15:16) 특실 매진, 일반실 매진, 예약대기 불가능
   [ ] [SRT 339] 01월 04일, 수서~동대구(13:55~15:25) 특실 매진, 일반실 예약가능, 예약대기 불가능
   [ ] [SRT 341] 01월 04일, 수서~동대구(14:30~16:10) 특실 매진, 일반실 매진, 예약대기 불가능

[?] 선택 유형 (↕:이동, Enter: 완료, Ctrl-C: 취소): 일반실 우선
 > 일반실 우선
   일반실만
   특실 우선
   특실만

[?] 예매 시 카드 결제 (y/N): N

예매 대기 중... |   16 (00:00:15)


🎊예매 성공!!!🎊
[SRT] 01월 04일, 수서~동대구(13:00~14:46) 36800원(1석), 구입기한 01월 03일 16:57
8호차 5B (일반실) 어른/청소년 [36800원(700원 할인)]


[?] 메뉴 선택 (↕:이동, Enter: 선택): 예매 확인/취소
   예매 시작
 > 예매 확인/취소
   로그인 설정
   텔레그램 설정
   카드 설정
   역 설정
   나가기

[?] 열차 선택 (↕:이동, Enter: 선택, Ctrl-C: 취소): SRT
 > SRT
   KTX
   취소

[?] 예약 취소 (Enter: 결정): [SRT] 01월 04일, 수서~동대구(13:00~14:46) 36800원(1석), 구입기한 01월 03일 16:57
 > [SRT] 01월 04일, 수서~동대구(13:00~14:46) 36800원(1석), 구입기한 01월 03일 16:57
   텔레그램으로 예매 정보 전송
   돌아가기
```

## Troubleshooting

### ImportError: attempted relative import with no known parent package

이 오류는 srtgo를 pip로 설치하지 않고 직접 실행하려고 할 때 발생합니다.

**해결 방법:**

1. **올바른 설치 방법** (권장):
```bash
pip install srtgo -U
srtgo
```

2. **개발 모드로 설치** (소스코드에서):
```bash
# 프로젝트 루트 디렉토리에서
pip install -e .
srtgo
```

3. **직접 실행하지 마세요:**
```bash
# ❌ 잘못된 방법
python srtgo/srtgo.py

# ✅ 올바른 방법
pip install -e .
srtgo
```

### SSL Certificate Error (curl_cffi)

Windows 환경에서 SSL 인증서 오류가 발생하는 경우:

```
curl.CurlError: Failed to perform, curl: (60) SSL certificate problem: unable to get local issuer certificate
```

**해결 방법:**

1. **CA 인증서 업데이트:**
```bash
pip install --upgrade certifi
```

2. **환경 변수 설정** (임시 해결):
```bash
# Windows PowerShell
$env:CURL_CA_BUNDLE=""

# Windows CMD
set CURL_CA_BUNDLE=

# Linux/Mac
export CURL_CA_BUNDLE=""
```

3. **패키지 재설치:**
```bash
pip uninstall srtgo
pip install srtgo -U --no-cache-dir
```

### 의존성 설치 문제

requirements.txt를 사용한 수동 설치:

```bash
# 런타임 의존성만 설치
pip install -r requirements.txt

# 개발 의존성도 함께 설치
pip install -r requirements-dev.txt
```

### Telegram 오류: Chat not found / BadRequest

텔레그램 알림 사용 시 다음과 같은 오류가 발생하는 경우:

```
Exception: Chat not found, Type: <class 'telegram.error.BadRequest'>
```

**원인:**
- 잘못된 Chat ID 입력
- Bot Token이 올바르지 않음
- 봇과 대화를 시작하지 않음

**해결 방법:**

1. **봇과 대화 시작:**
   - 텔레그램에서 본인의 봇을 찾아 `/start` 명령 전송
   - 봇과의 대화방이 생성되어야 메시지를 받을 수 있습니다

2. **올바른 Chat ID 확인:**
   ```bash
   # 다음 URL로 Chat ID 확인 (YOUR_BOT_TOKEN을 실제 토큰으로 교체)
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
   - 브라우저에서 위 URL 접속
   - `"chat":{"id":숫자}` 부분에서 Chat ID 확인
   - [자세한 가이드](https://gabrielkim.tistory.com/entry/Telegram-Bot-Token-%EB%B0%8F-Chat-Id-%EC%96%BB%EA%B8%B0)

3. **텔레그램 설정 다시 입력:**
   ```bash
   srtgo
   # 메뉴에서 "텔레그램 설정" 선택
   # Bot Token과 Chat ID 정확히 재입력
   ```

4. **텔레그램 기능 사용하지 않기:**
   - 예매 시 카드 결제를 묻는 질문에서 `N` 선택
   - 텔레그램 설정 없이도 예매 가능

## Acknowledgments
- This project includes code from [SRT](https://github.com/ryanking13/SRT) by ryanking13, licensed under the MIT License, and [korail2](https://github.com/carpedm20/korail2) by carpedm20, licensed under the BSD License.
