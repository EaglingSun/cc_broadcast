# cc_broadcast — 강사 프롬프트 받기

강사가 방송한 프롬프트를 내 Claude Code 입력창에 **초안으로** 받는 mod(`prompt-cast-recv`)를 설치한다. 보내기(Enter)는 언제나 내가 한다.

## 설치 — 한 번만 (PowerShell)

```powershell
git clone https://github.com/EaglingSun/cc_broadcast C:\lab\cc_broadcast
cd C:\lab\cc_broadcast
py -3.13 setup\prompt-cast\install.py
```

마지막 줄 대신 이 폴더에서 `claude` 를 열고 「프롬프트 방송 설치해 줘」라고 해도 된다.

- 표 끝이 OK · 종료 코드 0 이면 끝이다.
- **사용자 범위 설치다** — 실습 저장소가 바뀌어도 다시 깔지 않는다. 어느 저장소 창에서든 받는다.
- **이 폴더(`C:\lab\cc_broadcast`)는 지우거나 옮기지 않는다** — mod 가 여기서 바로 읽힌다. 옮겼으면 새 위치에서 다시 설치한다.
- 설치 전에 열어 둔 Claude 창은 `/reload-plugins` 를 치거나 새 창을 연다.
- 종료 코드 3(같은 이름이 다른 폴더로 등록돼 있음) → `py -3.13 setup\prompt-cast\install.py --replace`
- 종료 코드 2(claude 버전 낮음) → `claude update` 뒤 새 터미널에서 다시. 2.1.292 이상이어야 한다.

## 강의 때

1. 강사 화면의 줄을 Claude Code 프롬프트 칸에 그대로 입력한다: `/cast-connect 강사IP:8790`
2. 방송이 오면 입력창이 비어 있을 때 초안으로 들어온다 → 고친 뒤 Enter. 쓰던 글이 있으면 덮지 않고 입력창 위에 「#N 도착 [넣기] [뒤에 붙이기]」가 뜬다.
3. 지난 방송은 `/cast`.
4. 상태줄 「📡 강사 연결 안 됨」이면 주소가 강사 화면 줄과 같은지 보고, 같으면 강사에게 알린다.

## 지우기

```powershell
claude plugin marketplace remove sure-lab-cast
```
