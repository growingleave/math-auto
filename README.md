# math-auto

구글 드라이브(또는 로컬 폴더)에 흩어져 있는 수학 문제 사진 + 정답 사진을 자동으로 짝지어서, 문제집 형식(문제 섹션 + 뒤쪽 정답 섹션)의 PDF 한 권으로 모아주는 도구입니다.

실제 드라이브 폴더가 어떻게 정리되어 있는지 미리 알 수 없는 상황을 가정하고 만들었습니다. 그래서 문제/정답 짝짓기는 여러 명명 규칙을 순서대로 시도하고, 확신할 수 없는 건 추측하지 않고 "확인 필요" 목록으로 분리합니다.

## 두 가지 모드

- **`compile` (기본, 추천)**: 사진 내용을 다시 읽지 않고 **원본 사진을 그대로** PDF에 배치합니다. 사진이 이미 깨끗하면(인쇄된 문제, 타이핑되거나 또렷한 손글씨 정답) 이 모드만으로 충분하고, 파일명/폴더 구조가 뚜렷하면 **AI API 호출이 전혀 필요 없습니다.**
- **`build`**: Claude Vision으로 사진 속 글자를 읽어 텍스트로 재구성한 뒤 다시 타이핑된 형태로 PDF를 만듭니다. 매 장마다 API 호출이 들어가고 비용이 발생하며, 인식이 틀릴 수 있어 검토가 필요합니다. 사진 품질이 나쁘거나 정리된 텍스트가 필요할 때만 사용하세요.

둘 다 매칭(짝짓기) 로직은 동일하게 공유합니다.

## 동작 과정 (compile 기준)

```
파일 목록 조회 -> 문제/정답 짝짓기 -> 원본 사진을 PDF 페이지에 배치 -> 업로드
```

### 지원하는 짝짓기 방식

1. **폴더분리형**: `문제`/`정답`, `problems`/`answers` 처럼 역할별로 폴더가 나뉘어 있는 경우. 파일명에 번호가 있으면 번호로, 없으면 정렬 순서로 짝지음.
2. **파일명마커형**: 한 폴더 안에 `01_문제.jpg`/`01_정답.jpg`, `ch3_question.png`/`ch3_answer.png`, `q1.jpg`/`a1.jpg` 처럼 파일명 자체에 역할이 드러나는 경우.
3. **숫자시퀀스 + Vision 분류**: 아무 마커도 없이 번호만 있는 경우, 이미지 내용을 보고 "문제인지 정답인지" Claude에게 분류를 맡겨서 짝지음 (`--no-vision-classify`로 끌 수 있음).

세 방식 모두로 짝을 못 찾은 파일은 `unmatched`, 역할이 같은 파일 둘이 묶이는 등 애매한 경우는 `ambiguous`로 리포트에 남습니다.

## 설치

```bash
pip install -r requirements.txt
playwright install chromium
```

필요한 자격증명:
- 구글 드라이브를 쓸 경우: 서비스 계정 JSON 키 파일 (아래 참고)
- `ANTHROPIC_API_KEY` 환경변수: `build` 모드를 쓸 때, 또는 `compile` 모드에서 파일명/폴더만으로 역할(문제/정답)을 판단할 수 없는 애매한 파일이 있어 Vision 분류를 쓸 때 필요. 명명 규칙이 뚜렷하면 `compile` + `--no-vision-classify`는 API 키가 전혀 필요 없습니다.

## 먼저 로컬로 테스트해보기 (자격증명 없이)

실제 드라이브에 연결하기 전에, 로컬 폴더 구조로 매칭 + PDF 생성까지 전부 확인할 수 있습니다.

```bash
mkdir -p sample/문제 sample/정답
# 실제 사진 파일을 넣어보세요 (문제/01.jpg, 정답/01.jpg 등)

PYTHONPATH=src python -m mathauto match --source local:sample --no-vision-classify   # 짝짓기만 미리 확인
PYTHONPATH=src python -m mathauto compile --source local:sample --no-vision-classify  # 원본 사진으로 PDF까지 생성
# sample/output/workbook.pdf 에 생성됨
```

텍스트를 다시 추출해서 재조판된 PDF가 필요하면 (`ANTHROPIC_API_KEY` 필요):

```bash
PYTHONPATH=src python -m mathauto build --source local:sample
```

## 구글 드라이브 연결 설정

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 만들고 **Google Drive API**를 활성화합니다.
2. **서비스 계정**을 만들고 JSON 키를 발급받습니다 (IAM 및 관리자 > 서비스 계정 > 키 추가).
3. 발급받은 서비스 계정 이메일(`xxx@xxx.iam.gserviceaccount.com`)을, 읽을 드라이브 폴더와 결과를 저장할 폴더에 **공유 대상으로 추가**합니다 (뷰어/편집자 권한).
4. 드라이브 폴더 URL의 `.../folders/` 뒤에 있는 값이 폴더 ID입니다.

```bash
PYTHONPATH=src python -m mathauto match \
  --source drive:<문제_폴더_ID> \
  --credentials ./service-account.json

PYTHONPATH=src python -m mathauto compile \
  --source drive:<문제_폴더_ID> \
  --output drive:<결과_저장_폴더_ID> \
  --credentials ./service-account.json
```

## CLI 명령어

- `mathauto match --source <소스>` : 실제 생성 없이 매칭 결과만 확인 (dry run). `--format json`으로 JSON 출력 가능.
- `mathauto compile --source <소스> [--output <소스>]` : 매칭 -> 원본 사진을 그대로 PDF에 배치 -> 업로드. **기본 추천 명령.**
- `mathauto build --source <소스> [--output <소스>]` : 매칭 -> Vision으로 텍스트 재추출 -> PDF 생성 -> 업로드. 사진이 지저분하거나 재조판된 텍스트가 필요할 때만.

둘 다 `--output` 생략 시 `--source`와 같은 위치에 저장됩니다.

`<소스>`는 `local:<경로>` 또는 `drive:<폴더ID>` 형식입니다.

## 알려진 한계 (다음에 다룰 부분)

- `compile` 모드는 사진 크기가 제각각이면 한 페이지에 몇 개씩 들어가는지 자동으로 흘려 배치합니다(사진이 작을수록 더 많이 들어감). 정확히 몇 개씩 고정된 격자로 넣고 싶다면 아직 옵션이 없습니다.
- `build` 모드는 손글씨 인식이 틀릴 수 있습니다. 결과에 추출 실패 목록과, 모델이 스스로 "확신 없음"이라고 표시한 항목(`notes`)이 함께 나오니 PDF를 쓰기 전에 한 번 검토하는 걸 권장합니다.
- 챕터별로 `문제`/`정답` 폴더가 여러 개 중첩된 구조(예: `1단원/문제`, `2단원/문제`)는 아직 지원하지 않습니다. 현재는 드라이브 폴더 전체에서 "문제" 역할 폴더/"정답" 역할 폴더가 각각 정확히 하나씩일 때만 폴더분리형 전략이 적용됩니다.
- 단원/난이도 태깅, 중간 리뷰·수정 UI는 아직 없습니다 (MVP 범위 밖).
