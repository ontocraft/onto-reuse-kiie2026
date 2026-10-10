# 제조 온톨로지 재사용 사례: 재현 자료

양선희, 이두원(OntoCraft), 「제조 온톨로지를 재사용할 때 유지해야 하는 구분: 정비·품질·공정
공개 자료의 선행조사」, 2026 대한산업공학회 추계학술대회 발표 예정 논문의 재현 자료이다.

Reproduction materials for "Distinctions to Preserve When Reusing Manufacturing Ontologies"
(KIIE Fall Conference 2026, to appear). Competency questions, requirement-element
assignments, the derived schema, and analysis scripts.

## 들어 있는 것

| 파일 | 내용 |
|---|---|
| `competency_questions.csv` | 역량 질문 26개, 질문별 요구 요소, 배정 상태(`assigned` 22 · `partial` 4), 메모 |
| `schema/제조-공통스키마.json` | 질문에 맞춰 공개 정의를 대응한 스키마. 각 요소의 IOF·QIF 출처 |
| `scripts/mfg_reuse.py` | IOF 분야별 모듈의 공통 클래스 직접상위 참조 비율(논문 4절) |
| `scripts/mfg_schema.py` | 스키마의 IOF 대응 검사, 역할로 정의된 클래스 집계(6.2절) |
| `scripts/mfg_qif.py` | QIF 타입의 정의 필드와 공개 측정 파일의 관측 필드(5절) |
| `scripts/mfg_cover.py` | 역량 질문과 스키마 요소의 대조(7절) |
| `scripts/mfg_hermit.py` | 역할 정의 클래스 4개의 HermiT 분류(6.2절) |
| `scripts/mfg_x1_run.py` | 질문 X1을 SPARQL로 실행해 끊기는 연결을 확인(7절) |

배정은 연구자 한 명이 정의를 읽고 판정한 결과이다. `assigned`는 필요한 정의가 스키마에
있다는 뜻이며, 질의에 답했다는 뜻이 아니다. `mfg_x1_run.py`의 단계 B와 C는 지어낸 시험
데이터를 넣는다. 스크립트 안의 설명과 주석은 한국어이다. 스키마와 질문 표의 「재료 인공물」은 IOF의
`MaterialArtifact`이며 논문에서는 「물질 인공물」로 적었다. 스크립트 주석이 가리키는 내부 문서(`docs/…`)와
결정기록 번호는 이 패키지에 들어 있지 않다.

## 들어 있지 않은 것

공개 배포판과 측정 파일은 재배포하지 않는다. 아래 주소에서 받아 `data/ontology/` 아래에
둔다. 논문은 괄호 안의 날짜에 받은 판을 썼다.

| 자료 | 주소 | 둘 곳 |
|---|---|---|
| IOF (2026-09-18) | https://github.com/iofoundry/ontology | `data/ontology/iof-src/<모듈>__<파일>.rdf` |
| QIF 3.0 xsd (2026-09-30) | https://qifstandards.org | `data/ontology/ext/*.xsd` |
| QIF 측정 파일 2개 | https://github.com/QualityInformationFramework/qif-workshop `models/` | `data/ontology/ext/표본454.qif`, `표본473.qif` |
| BFO 2020 (2026-10-10) | http://purl.obolibrary.org/obo/bfo/2020/bfo.owl | `data/ontology/ext/bfo-2020.owl` |

```bash
# IOF: 모듈 디렉터리의 .rdf 를 <모듈>__<파일> 이름으로 모은다
git clone --depth 1 https://github.com/iofoundry/ontology /tmp/iof
mkdir -p data/ontology/iof-src data/ontology/ext
for m in core maintenance productionplanning supplychain productservicesystem certification biopharma migration; do
  for f in /tmp/iof/$m/*.rdf; do cp "$f" "data/ontology/iof-src/${m}__$(basename "$f")"; done
done

# QIF 3.0 xsd
curl -sL -o /tmp/QIF3.zip "https://qifstandards.org/wp-content/uploads/2014/08/QIF3.0-2018-ANSI.zip"
unzip -q -o /tmp/QIF3.zip 'xsd/*' -d /tmp/qif3
cp /tmp/qif3/xsd/QIFLibrary/*.xsd /tmp/qif3/xsd/QIFApplications/*.xsd data/ontology/ext/

# QIF 측정 파일
B=https://raw.githubusercontent.com/QualityInformationFramework/qif-workshop/HEAD/models
curl -sL -o data/ontology/ext/표본454.qif $B/000454_D-MV-FH-2.qif
curl -sL -o data/ontology/ext/표본473.qif $B/000473_A-MV-FH.qif

# BFO 2020
curl -sL -o data/ontology/ext/bfo-2020.owl http://purl.obolibrary.org/obo/bfo/2020/bfo.owl
```

배포판이 갱신되면 값이 달라질 수 있다. 논문의 값과 다르면 받은 날짜부터 확인한다.

## 실행

Python 3.11 이상. `mfg_hermit.py`는 Java가 필요하다.

```bash
pip install -r requirements.txt
python scripts/mfg_reuse.py modules     # 919 · 300 · 81
python scripts/mfg_schema.py roles      # 70 · 35 중 4
python scripts/mfg_qif.py sample        # 64 중 8 · ManufacturingProcessId 0
python scripts/mfg_cover.py             # 26 · 22 · 4 · 0
python scripts/mfg_hermit.py            # 4 / 4
python scripts/mfg_x1_run.py            # 부적합 224 · 실제 자료 답 0
```

스크립트는 이 디렉터리를 작업 디렉터리로 두고 실행한다.

## 라이선스

코드는 MIT, `competency_questions.csv`와 스키마 JSON은 CC BY 4.0이다. IOF는 MIT 라이선스이고,
QIF와 BFO는 각 배포처의 조건을 따른다.
