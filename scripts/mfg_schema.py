"""제조 정비 AI 공통 스키마를 JSON 으로 내보내고 IOF 대응을 검사합니다.

    .venv/bin/python scripts/연구/mfg_schema.py check    # IOF 대응이 실제로 있는지 봅니다
    .venv/bin/python scripts/연구/mfg_schema.py export   # schema/ 에 JSON 을 씁니다

`docs/연구/제조-공통스키마.md` 의 3 장과 7 장을 데이터로 옮겨 적은 것입니다. 문서가
설명이고 이 파일이 기계가 읽는 정본입니다. 둘이 갈라지지 않게 하려고 IOF 대응을
`data/ontology/iof-src/` 의 배포판에서 직접 확인합니다. 클래스 이름을 잘못 적으면
`check` 가 실패합니다.

`iof` 가 `null` 인 것은 표준에 없어 우리가 더한 클래스입니다. 지금 셋입니다.
예지 · 품질 특성 · 진단한다 관계입니다. 근거는 결정기록 0027 과 스키마 문서에 있습니다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

IOF_SRC = Path("data/ontology/iof-src")
OUT = Path("schema/제조-공통스키마.json")
IOF_BASE = "https://spec.industrialontologies.org/ontology/construct/"

VERSION = "2026-09-29"
MAINTENANCE_RELEASE = "202603"

# (우리 이름, IOF 지역 이름 또는 None, 갈래, 설명)
CLASSES = [
    ("정비 대상", "MaintainableMaterialItem", "사물",
     "⚠️ **역할로 정의된 클래스다.** `(MaterialArtifact ∨ EngineeredSystem) ∧ "
     "∃r(MaintainableMaterialItemRole(r) ∧ hasRole(x,r))` 다. 설비와 부품을 "
     "아우르는 상위 클래스가 아니다. 셋 다 BFO_0000040 아래 형제다"),
    ("설비", "PieceOfEquipment", "사물",
     "⚠️ **역할 정의다.** 설명 주석이 「구체적인 설비 **종류**는 material artifact 나 "
     "engineered system 아래 선언하고 piece of equipment 아래 직접 두지 말라」고 한다. "
     "**종류를 두지 말라는 것이고 개체를 금지하는 것이 아니다.** 물질 인공물이면서 "
     "설비 역할을 가진 개체는 정의에 따라 여기 속한다"),
    ("부품", "MaterialComponent", "사물", ""),
    ("재료", "RawMaterial", "사물", "가공 전 재료"),
    ("재료 인공물", "MaterialArtifact", "사물",
     "만들어진 물체. **종류를 선언하는 자리다.** 역할 정의가 아니다. 공작기계·베어링 "
     "같은 종류를 여기 아래 둔다"),
    ("공학 시스템", "EngineeredSystem", "사물",
     "여러 부분이 함께 기능하도록 만든 것. 재료 인공물과 함께 인스턴스가 사는 자리다"),
    ("설비 역할", "EquipmentRole", "성질", "공정에서 장비로 쓰이는 역할"),
    ("분류자", "Classifier", "정보",
     "⚠️ **미적용.** `상위 개념이다`·`하위 개념이다` 의 양 끝이다. 우리 개념 노드는 "
     "분류자로 모형화하지 않았으므로 그 두 관계를 쓰지 않는다. 관계의 끝이 정의되지 "
     "않은 채로 두면 검사가 못 잡으므로 클래스로 둔다"),
    ("정비 대상 역할", "MaintainableMaterialItemRole", "성질", "정비를 받는 역할"),

    ("정비 상태", "MaintenanceState", "상태", ""),
    ("정상 가동", "OperatingState", "상태", ""),
    ("열화 상태", "DegradedState", "상태",
     "주기능은 되고 역량 하나 이상이 안 된다"),
    ("고장 상태", "FailedState", "상태",
     "주기능이 실현되지 않는다. 열화와 가르는 기준이 이것이다. broken · unserviceable"),

    ("고장 과정", "FailureProcess", "과정", "leaking · overheating 이 듭니다"),

    # ⚠️ **상태는 한 축이 아니다** (2026-09-30, FOMI 2021 paper22).
    #    위 셋은 설비 자체의 건강 축이고, 아래 둘은 외부 주체가 켜고 끈 축이다.
    #    **동시에 적용된다.** 꺼져서 안 되는 것과 고장 나서 안 되는 것은 다르다.
    ("고장 발현", "FailureEffect", "과정", ""),
    ("정상 기능 수행", "FunctioningProcess", "과정", ""),
    ("가공 공정", "ManufacturingProcess", "과정", ""),
    ("고장 사건", "FailureEvent", "과정", "상태를 바꾸는 시점"),

    ("켜짐 상태", "MaintenanceState", "상태",
     "⚠️ 외부 작용 축. IOF 배포판에 별도 클래스를 찾지 못해 상위로 둔다"),
    ("꺼짐 상태", "MaintenanceState", "상태",
     "⚠️ 위와 같다. 대부분의 정비는 이 상태에서만 할 수 있다"),

    ("정비 활동", "MaintenanceActivity", "활동", ""),
    ("정비 과정", "MaintenanceProcess", "활동", ""),
    ("보조 정비 활동", "SupportingMaintenanceActivity", "활동", ""),
    ("계측", "MeasurementProcess", "활동", ""),
    ("진단", "MaintenanceActivity", "활동",
     "MaintIE 의 MaintenanceActivity/Diagnose 를 그대로 씁니다"),
    ("예지", None, "활동",
     "IOF 42 모듈에 없습니다. 진단의 형제로 둡니다. 잔여수명 · 열화 추세 예측"),

    ("공정 변수", "ProcessCharacteristic", "성질", ""),
    ("요구 기능", "RequiredFunction", "성질", ""),
    ("고장 성향", "DispositionToFail", "성질", ""),
    ("바람직하지 않은 성향", "UndesireableDisposition", "성질",
     "고장 성향의 상위. ⚠️ 표준에 `Undesireable` 로 철자가 틀린 채 들어가 있다"),
    ("품질 특성", None, "성질",
     "core 에 없습니다. biopharma 의 QualityAttribute 뿐이라 BFO_0000019 아래 둡니다"),

    ("정비원", "QualifiedMaintenancePerson", "사람",
     "iof-maint 의 20 개 중 하나인데 2026-09-30 까지 가져오지 않고 있었다. "
     "우리 스키마에 사람이 한 명도 없었다"),

    ("작업지시", "MaintenanceWorkOrderRecord", "정보", ""),
    ("자격 명세", "QualificationSpecification", "정보",
     "전기 기능 자격 · 용접 자격 같은 것. RequirementSpecification 의 하위"),
    ("고장 모드 코드", "FailureModeCode", "정보", ""),
    ("정비 전략", "MaintenanceStrategy", "정보", ""),
    ("위험 추정", "RiskEstimate", "정보",
     "⚠️ **biopharma 모듈에 있다.** 정의는 도메인 중립이다. 모듈을 가져오지 않고 "
     "이름만 근거로 쓴다. 잔여 위험은 ResidualRiskEstimate 다"),
]

# (우리 이름, IOF 지역 이름 또는 None, 출발, 도착, 적용 조건)
#
# ⚠️ **이름이 맞는다고 옳은 대응이 아니다.** 2026-09-29 외부 검토가 지적했고,
#    IOF 의 domain · range 로 확인하니 우리 대응 셋이 실제로 틀려 있었다.
#    `measuresAtSomeTime` 의 domain 은 계측 과정이 아니라 계측 장치이고,
#    `prescribes` 의 domain 은 사람이 아니라 정보 개체이며,
#    `hasMaterialState` 의 range 는 MaterialState 라 우리 정비 상태가 아니다.
#    `check` 가 이제 domain · range 도 함께 본다.
RELATIONS = [
    ("부품을 가진다", "hasComponentPartAtAllTimes", "설비", "부품",
     "영구 부품에만 쓴다. 정의의 예가 차체와 섀시다. 교체되는 베어링의 현재 장착은 "
     "이 관계가 아니다"),
    ("재료로 이루어진다", "isMadeOfAtAllTimes", "부품", "재료", ""),
    ("측정한다", "measuresAtSomeTime", "계측 장치", "공정 변수",
     "출발은 계측 장치다. 계측 과정이 아니다. 정의의 예가 온도 센서다"),
    ("산출한다", "hasOutput", "가공 공정", "재료 인공물", ""),
    ("상위 개념이다", "generalizes", "분류자", "분류자",
     "domain · range 가 Classifier 다. 개념 노드를 분류자로 모형화한 경우에만 쓴다. "
     "지금 우리 개념 노드는 분류자가 아니므로 미적용"),
    ("하위 개념이다", "specializes", "분류자", "분류자", "위와 같다"),
    ("정비 상태를 가진다", "hasMaintenanceState", "정비 대상", "정비 상태", ""),
    ("일으킨다", "causes", "고장 과정", "고장 발현",
     "상태를 매개한 전이 인과다. 과정과 사건 사이에만 쓴다. 성질로 나타나는 증상에는 "
     "쓰지 않는다"),
    ("상태를 개시한다", "initiates", "고장 사건", "고장 상태", ""),
    ("기술한다", "describes", "작업지시", "정비 과정", ""),
    ("투입된다", "isInputOf", "작업지시", "정비 과정", ""),
    ("입력을 가진다", "hasInput", "정비 과정", "정비 대상", ""),
    ("전략에 따른다", "prescribedBy", "정비 과정", "정비 전략", ""),
    ("지시한다", "prescribes", "정비 전략", "정비 활동",
     "출발은 정보 개체다. 사람이 아니다. 정의의 예가 청사진과 작업계획서다"),
    ("기능이다", "functionOf", "요구 기능", "정비 대상", ""),
    ("진단한다", None, "진단", "고장 상태",
     "IOF 에 대응이 없다. 우리가 더한다. "
     "⚠️ **어느 질문에도 쓰이지 않는다.** M3 은 MQTO 의 지표 평가 경로로 답한다. "
     "그쪽은 정보 개체(지표 평가)에서 잇고 이쪽은 활동(진단)에서 잇는다. "
     "**둘 중 어느 쪽을 쓸지 정하지 않았으므로 남긴다.** 정하면 하나를 뺀다"),
    ("이 상태를 요구한다", None, "정비 활동", "정비 상태",
     "⚠️ 우리가 더한다. 대부분의 정비는 꺼짐 상태를 요구하고 교정은 켜짐 상태를 "
     "요구한다(FOMI 2021 paper22). 활동과 상태를 잇는 것이 없었다"),
    ("고장을 인지한다", "recognizesAtSomeTime", "정비원", "고장 사건",
     "정의의 예가 「작업자가 고장 사건을 인지한다」다. 사람이 무엇을 발견했는지 남긴다"),
    ("설비를 가리킨다", None, "공정 실행 기록", "재료 인공물",
     "⚠️ **우리가 더한다.** QIF 는 설비를 `MachineIdentifier`(xs:string)로만 담고 "
     "노드로 잇지 않는다. 문자열을 개체에 맞추는 것이 이 연구가 만들 자리다"),
    ("역할을 가진다", "hasRole", "재료 인공물", "설비 역할",
     "domain 은 IndependentContinuant 이고 range 는 Role 이다. "
     "같은 개체가 설비 역할과 정비 대상 역할을 함께 가진다. **X1 이 이것을 쓴다**"),
    ("자격을 만족한다", "satisfiesRequirement", "정비원", "자격 명세",
     "domain 이 BFO 개체이고 range 가 RequirementSpecification 이다. 자격 명세가 "
     "그 하위다. **R1 의 빠진 관계가 이것이었다.** 만들 것이 아니었다"),
    ("가용하다", "isAvailableToAtSomeTime", "부품", "정비원",
     "정의의 예가 「알루미늄 롤(자원)이 누구에게 가용하다」다. range 만 Agent 로 "
     "선언되어 있고 domain 은 없다"),
]

# ⚠️ **정비원과 자격 명세를 잇는 관계를 찾지 못했다.** `QualifiedMaintenancePerson`
#    의 정의문이 자격 명세를 언급하지만 그 둘을 잇는 object property 가 무엇인지
#    확인하지 못했다. `prescribedBy` 가 형태상 맞으나 정의의 예가 청사진과 작업
#    계획서라 사람에게 쓰는 것이 맞는지 알 수 없다. **지어내지 않고 비워 둔다.**

COMMON_ATTRS = [
    ("이름", "문자열", "필수", "원본 표기 그대로"),
    ("정규화 이름", "문자열", "필수", "괄호 제거 · 소문자 · 공백 정리"),
    ("클래스", "문자열", "필수", "CLASSES 의 우리 이름"),
    ("출처", "열거", "필수", "iof · workorder · manual · literature"),
    ("출처 식별자", "문자열", "선택", "IOF IRI · 작업지시 번호 · OpenAlex keyword id"),
    ("판정 근거", "열거", "필수", "표준 · 사람 · 규칙"),
    ("규칙 버전", "문자열", "조건부", "판정 근거가 규칙일 때"),
    ("확인일", "날짜", "조건부", "판정 근거가 사람일 때"),
]

CLASS_ATTRS = {
    "설비": ["설비 번호", "설치일", "제조사", "모델", "functionClass"],
    "정비원": ["식별자", "보유 자격"],
    "자격 명세": ["자격 이름", "발급 기관", "유효 기간"],
    "부품": ["부품 번호", "교체 주기", "수명 기준", "functionClass", "일련번호"],
    "정비 상태": ["상태 값", "관측 시각"],
    "고장 상태": ["고장 모드 코드", "중대도", "발생 가능성", "검출도"],
    "고장 과정": ["신호 종류", "단위", "측정 위치"],
    "공정 변수": ["단위", "정상 범위"],
    "품질 특성": ["단위", "공차"],
    "정비 활동": ["정비 유형", "소요 시간", "정비 시각", "인건비", "자재비"],
    "정비 전략": ["위험 추정", "잔여 위험", "기대 이익"],
    "작업지시": ["지시 번호", "발행일", "완료일", "담당자"],
    "특성 명세": ["공차값", "단위", "데이텀", "재료 조건"],
    "특성 측정": ["측정값", "최대값", "최소값", "적합 판정",
             "측정 시각", "부적합 번호"],
    "공정 실행 기록": ["작업 번호", "리비전", "설비 식별자", "작업자 식별자",
                "교대", "부서", "공정 변수 목록"],
    "검사 실행 기록": ["검사 시작", "검사 종료", "검사자", "보고서 번호", "검사 범위"],
    "계측 장치": ["장치 갈래", "제조사", "모델 번호", "일련번호", "위치"],
    "교정": ["교정 시각", "만료 시각", "교정 기준기"],
    "지표": ["하한", "상한", "항목 창 크기", "시간 창 크기", "평가 방법"],
    "지표 평가": ["계산값", "판정", "계산 시각"],
    "시행 조치": ["점수", "완료 시각"],
    "고장 사건": ["발생 시각"],
}

REL_ATTRS = {
    "일으킨다": ["신뢰도", "근거"],
    "상위 개념이다": ["판정 근거", "규칙 버전", "검수 여부"],
    "입력을 가진다": ["시각"],
}

# functionClass 의 값 체계. 출처를 확인했습니다.
FUNCTION_CLASS = {
    "표준": "IEC 81346-2:2019",
    "제목": ("Industrial systems, installations and equipment and industrial products "
           "— Structuring principles and reference designations — Part 2: "
           "Classification of objects and codes for classes"),
    "발행": "IEC, Geneva, 2019",
    "층": {"2단": 19, "3단": 173},
    "경유": "MaintIE SCHEME.md 가 이 표준의 기능 기반 객체 분류를 그대로 씁니다",
    "주의": "표준 원문은 유료입니다. 정식 인용 전에 확보해야 합니다",
}


# ────────────────────── IOF 밖에서 가져온 것 ──────────────────────
#
# ⚠️ **IOF 배포판에 없으므로 `check` 가 대조하지 않는다.** 출처와 파일을 적어
#    두고 사람이 확인한다. IOF 것과 섞으면 무엇이 표준이고 무엇이 아닌지 흐려진다.
#
# 2026-09-30 에 정비 절차 온톨로지 파일을 읽고 더했다. 안전·순서·자원이 우리
# 스키마에 통째로 빠져 있었다.

EXT_SOURCE = {
    "절차": {
        "이름": "Maintenance Procedure Ontology",
        "출처": "github.com/uwasystemhealth/Paper_Archive_Procedure_Ontology",
        "파일": "static-procedure-ontology.owl",
        "논문": "Woods et al. 2023, Applied Ontology 18(2), doi:10.3233/AO-230279",
        "확인": "파일에서 선언을 확인. **논문 본문은 읽지 않았다**",
    },
    "진단": {
        "이름": "MQTO 1.0 (Manufacturing Quality Troubleshooting Ontology)",
        "출처": "w3id.org/mqto/1.0",
        "파일": "mqto-1.0.ttl",
        "논문": "Bischof et al. 2026, MQTO Version 1.0",
        "확인": "파일에서 선언과 domain·range 를 확인. 클래스 29 · 객체 속성 37 · "
              "데이터 속성 17. LIS-14 의 Specified·Actual 과 SOSA/SSN 위에 있다. "
              "⚠️ 2026-09-30 까지 이 파일을 「클래스 27 · 관계 36」으로만 세고 "
              "내용을 읽지 않았다",
    },
    "품질": {
        "이름": "QIF 3.0 (ANSI / ISO 23952:2020)",
        "출처": "qifstandards.org · github.com/QualityInformationFramework",
        "파일": "배포판 xsd 22 개 (QIF3.0-2018-ANSI.zip) · "
              "qif-workshop/models/000454_D-MV-FH-2.qif (실물 표본)",
        "논문": "표준 문서. ISO 23952:2020",
        "확인": "⚠️ **OWL 이 아니라 XML Schema 다.** 아래 이름은 XSD 요소 이름이고 "
              "관계는 id 참조 필드(keyref)다. 클래스와 객체 속성이 아니다. "
              "2026-09-30 에 측정 표본 하나(부품 15 개)에서 참조 사슬을 확인했다. "
              "같은 날 배포판을 받아 타입 정의까지 확인했다(scripts/연구/mfg_qif.py). "
              "⚠️ 루트 스키마만 읽고 「표준에 없다」고 적었던 것을 정정했다. "
              "타입 정의는 하위 라이브러리에 있다",
    },
}

# (우리 이름, 출처, 그쪽 지역 이름, 갈래, 설명)
EXT_CLASSES = [
    ("위험", "절차", "Hazard", "성질", "정비 작업에 따르는 위험"),
    ("정비 중 위험", "절차", "HazardInMaintenanceProcess", "성질", ""),
    ("허가", "절차", "Permit", "정보", "작업 전에 받아야 하는 것"),
    ("자원", "절차", "Resource", "사물", "공구 · 자재 등 작업에 쓰는 것"),
    ("정비 작업", "절차", "MaintenanceTask", "활동", "절차를 이루는 한 단위"),
    ("절차 문서", "절차", "MaintenanceProcedureDocument", "정보", ""),

    # QIF 는 특성을 네 겹으로 나눈다. LIS-14 의 Specified · Actual 두 겹보다 깊다.
    # 2026-09-30 측정: 명세 24 · 설계 24 · 항목 157 · 측정 600 (부품 15 개)
    # ⚠️ 네 겹은 유형과 개체를 가르는 축이 아니다. 성향과 실현, 명세와 실적, 그리고
    #    이 넷은 서로 다른 것을 가른다. 층의 수로 견주지 않는다.
    ("특성 명세", "품질", "CharacteristicDefinition", "정보",
     "공차값과 데이텀을 담는다. 부품의 어느 자리인지는 담지 않는다"),
    ("설계 특성", "품질", "CharacteristicNominal", "정보",
     "명세를 도면의 한 형상(FeatureNominal)에 걸어 놓은 것. 명세와 1 대 1 이었다"),
    ("특성 항목", "품질", "CharacteristicItem", "정보",
     "제품 구조에서 그 특성이 나타나는 개별 자리. FeatureItem 을 가리킨다. "
     "⚠️ **측정 대상 부품을 가리키지 않는다.** 표본 둘 196 건에서 자식이 네 종류였고"
     "(Name · Designator · FeatureItemIds · CharacteristicNominalId) 부품 참조가 없었다. "
     "다만 스키마는 항목 아래 LocationOnDrawing · MeasurementDeviceIds · "
     "NotableEventIds 를 허용한다. 계측 장치는 측정 대상 부품이 아니다. "
     "설계 24 에 항목 157 이 걸렸다"),
    ("특성 측정", "품질", "CharacteristicMeasurement", "정보",
     "측정값과 적합 판정. 판정값은 PASS · FAIL · UNDEFINED 셋을 관측했다. "
     "스키마 칸 10 개 가운데 표본이 채운 것은 4 개다"),

    # 아래 다섯은 2026-09-30 에 배포판을 받아 더했다. 전부 역량 질문에 걸린다.
    # ⚠️ 정의는 표준에 있고 공개 표본에는 비어 있다. 자료 확보가 따로 남는다.
    ("공정 실행 기록", "품질", "ManufacturingProcessTraceability", "정보",
     "어느 설비에서 누가 언제 만들었나. 칸 14 개. 표본은 요소조차 0 건이다"),
    ("검사 계획", "품질", "Plan", "정보",
     "어떤 특성을 어떤 방법으로 재라고 하는가. QIFPlan.xsd 에 타입 59 개가 있다"),
    ("검사 방법", "품질", "ActionMethodBase", "정보",
     "장비 갈래마다 하나씩 있다. 좌표측정기 · 게이지 · 레이저트래커 등"),
    ("검사 실행 기록", "품질", "InspectionTraceability", "정보",
     "검사 시각과 검사자와 참조한 계획. 칸 24 개. 표본은 15 건 전부 비어 있다"),
    ("계측 장치", "품질", "MeasurementResourceBase", "사물",
     "센서 · 공구 · 치구. QIFMeasurementResources.xsd 에 타입 147 개가 있다. "
     "이름 · 제조사 · 모델 번호 · 일련번호 · 위치를 담는다"),
    ("교정", "품질", "Calibration", "정보",
     "교정 시각과 **만료 시각**(minOccurs 1)을 담는다. 교정 기준기와 온도도 있다. "
     "**M4 가 계측기 쪽을 의심할 근거가 이것이다**"),

    # MQTO. 전부 역량 질문에 걸린다. LIS-14 의 명세·실적 짝을 그대로 가져온다.
    ("신호", "진단", "Signal", "정보",
     "데이터 채널의 명세. PLC 변수 · 아날로그 선 · 시계열 흐름이다. lis:Specified 아래. "
     "**센서 장치도 관측값도 아니다.** 실적 짝이 Property 다"),
    ("관측", "진단", "Observation", "활동",
     "센서 읽기 한 건. sosa:Observation 아래. 지표 평가의 근거가 된다"),
    ("지표", "진단", "Metric", "정보",
     "계산 방법과 상·하한을 담는 명세. 양적 센서 자료와 질적 고장 판정을 잇는다"),
    ("지표 평가", "진단", "MetricAssessment", "정보",
     "지표를 실행한 결과. 계산값을 상·하한과 견주어 참·거짓을 낸다. "
     "**이것이 고장 판정의 근거다.** lis:Actual 아래"),
    ("권장 조치", "진단", "Countermeasure", "활동",
     "고장 모드를 해소하는 절차의 **명세**. 단계 목록으로 되어 있다"),
    ("시행 조치", "진단", "CountermeasureExecution", "활동",
     "그 절차를 실제로 **수행한 것**. 권장과 시행을 가르는 것이 이 짝이다"),
    ("원인 범주", "진단", "FailureSourceCategory", "정보",
     "이시카와 5M 의 상위. 하위가 Machine · Manpower · Material · Measurement · "
     "Method 다섯이다. 우리 설비 · 정비원 · 재료 · 계측 · 가공 공정에 대응한다"),
]

# (우리 이름, 출처, 그쪽 지역 이름, 출발, 도착, 설명)
EXT_RELATIONS = [
    ("앞선다", "절차", "before", "정비 작업", "정비 작업", "순서. 사이에 다른 것이 있어도 된다"),
    ("바로 앞선다", "절차", "directlyBefore", "정비 작업", "정비 작업", "사이에 없다"),
    ("작업을 이룬다", "절차", "hasActivityPart", "정비 과정", "정비 작업", "부분 관계"),
    ("요구한다", "절차", "hasRequirement", "정비 작업", "자원", "무엇이 필요한가"),

    # ⚠️ 아래 넷은 객체 속성이 아니라 XSD 의 id 참조 필드다. 이름은 우리가 붙였다.
    ("명세에 따른다", "품질", "CharacteristicDefinitionId", "설계 특성", "특성 명세",
     "어느 공차를 적용했는가"),
    ("설계에 따른다", "품질", "CharacteristicNominalId", "특성 항목", "설계 특성",
     "이 자리가 도면의 어느 특성인가"),
    ("특성을 측정한다", "품질", "CharacteristicItemId", "특성 측정", "특성 항목",
     "측정 600 건이 특성 항목 152 개를 가리켰다"),
    ("부품을 가리킨다", "품질", "ActualComponentId", "특성 측정", "부품",
     "**측정 대상 부품이 들어오는 자리다.** 앞의 세 층에는 이 참조가 없다. "
     "QIF 는 일련번호로 식별한다"),

    # 2026-09-30 배포판에서 더한 여섯
    ("공정을 가리킨다", "품질", "ManufacturingProcessId", "특성 측정", "공정 실행 기록",
     "**품질에서 공정으로 가는 길이다.** 우리가 만들 자리라고 적었는데 표준에 있었다. "
     "⚠️ 도착은 공정 자체가 아니라 그 기록이다. QIF 의 키가 "
     "ManufacturingProcessTraceabilities 를 모은다"),
    ("이전 공정이다", "품질", "PreviousOperationId", "공정 실행 기록", "공정 실행 기록",
     "공정을 거슬러 올라간다"),
    ("장치로 측정한다", "품질", "MeasurementDeviceIds", "특성 측정", "계측 장치",
     "어느 장비로 쟀나. 특성 항목에도 같은 칸이 있다"),
    ("계획이 특성을 지시한다", "품질", "EvaluateCharacteristicMeasurand",
     "검사 계획", "특성 항목", "무엇을 재라고 하는가"),
    ("방법을 지정한다", "품질", "ActionMethods", "검사 계획", "검사 방법",
     "어떤 장비 갈래로 재라고 하는가"),
    ("계획을 따른다", "품질", "ReferencedQIFPlan", "검사 실행 기록", "검사 계획",
     "QIF 는 이 참조를 필수로 둔다(minOccurs 1)"),
    ("교정을 가진다", "품질", "Calibrations", "계측 장치", "교정",
     "장치마다 교정 기록이 붙는다"),

    # MQTO
    ("신호를 읽는다", "진단", "readsFrom", "지표", "신호", "어느 채널에서 계산하나"),
    ("관측에 근거한다", "진단", "basedOn", "지표 평가", "관측",
     "**M3 이 물은 「근거」가 이것이다.** 어느 읽기에서 계산했나"),
    ("고장을 낸다", "진단", "raised", "지표 평가", "고장 사건",
     "평가가 고장 발생을 일으킨다. 우리 `일으킨다`(과정→발현)와 다른 자리다"),
    ("조치를 권장한다", "진단", "suggested", "고장 사건", "시행 조치",
     "⚠️ MQTO 의 range 가 Countermeasure 가 아니라 CountermeasureExecution 이다. "
     "권장된 실행을 가리킨다. 그쪽 모형을 그대로 옮긴다"),
    ("조치로 해소한다", "진단", "mitigatedByExecution", "고장 사건", "시행 조치",
     "실제로 해소한 것. 위와 짝이며 **이 둘이 권장과 시행을 가른다**"),
    ("조치를 지시한다", "진단", "mitigates", "권장 조치", "고장 상태",
     "명세 층의 대응. MQTO 의 range 는 FailureMode 다"),
    ("범주에 든다", "진단", "failureBelongsTo", "고장 상태", "원인 범주",
     "**X3 이 물은 5M 축이 이것이다**"),
]

# ⚠️ **작업지시의 칸을 클래스로 두는 설계는 채택하지 않았다.**
#    `work-order-ontology.owl` 은 기록의 칸 하나하나를 클래스로 두고
#    `hasDataField` 로 단다. 칸마다 출처를 달 수 있으나 노드가 늘어난다.
#    우리는 속성 목록으로 둔다. **역량 질문으로 가릴 선택지로 남긴다.**


def declared() -> dict[str, str]:
    """IOF 배포판이 선언한 지역 이름과 그 모듈을 돌려줍니다."""
    out: dict[str, str] = {}
    pat = re.compile(r'<owl:(?:Class|ObjectProperty)[^>]*'
                     r'rdf:about="&iof-[a-z]+;([A-Za-z0-9_]+)"\s*>')
    for f in sorted(IOF_SRC.glob("*.rdf")):
        mod = f.name.split("__")[0]
        for m in pat.finditer(f.read_text(encoding="utf-8", errors="replace")):
            out.setdefault(m.group(1), mod)
    return out


def check() -> int:
    if not IOF_SRC.is_dir():
        print(f"IOF 배포판이 없습니다: {IOF_SRC}")
        return 2
    d = declared()
    print(f"IOF 선언 {len(d):,} 개를 읽었습니다 (파일 {len(list(IOF_SRC.glob('*.rdf')))})\n")

    bad, ours = [], []
    for kind, rows in (("클래스", CLASSES), ("관계", RELATIONS)):
        for row in rows:
            name, local = row[0], row[1]
            if local is None:
                ours.append((kind, name))
            elif local not in d:
                bad.append((kind, name, local))

    for kind, name, local in bad:
        print(f"없는 IOF 이름  {kind} {name} → {local}")
    print(f"우리가 더한 것 {len(ours)}: "
          + " · ".join(f"{n}({k})" for k, n in ours))

    # 클래스 속성과 관계 속성이 정의된 이름을 가리키는지도 봅니다
    cn = {c[0] for c in CLASSES} | {c[0] for c in EXT_CLASSES}
    rn = {r[0] for r in RELATIONS} | {r[0] for r in EXT_RELATIONS}

    # 외부 출처 관계의 양 끝이 정의된 클래스인지도 봅니다. 이름이 우리 것이라
    # IOF 대조로는 걸리지 않으므로 여기서 봐야 합니다.
    for name, src, local, dom, rng, _ in EXT_RELATIONS:
        for end in (dom, rng):
            if end not in cn:
                bad.append(("외부 관계", name, f"없는 클래스 {end}"))
                print(f"없는 클래스    {name} 의 끝 {end}")
    for name, _local, dom, rng, _cond in RELATIONS:
        for end in (dom, rng):
            if end not in cn:
                bad.append(("관계", name, f"없는 클래스 {end}"))
                print(f"없는 클래스    {name} 의 끝 {end}")
    for k in CLASS_ATTRS:
        if k not in cn:
            bad.append(("속성", k, "정의되지 않은 클래스"))
            print(f"없는 클래스    속성 표의 {k}")
    for k in REL_ATTRS:
        if k not in rn:
            bad.append(("속성", k, "정의되지 않은 관계"))
            print(f"없는 관계      속성 표의 {k}")

    if bad:
        print(f"\n실패. 맞지 않는 것 {len(bad)} 건")
        return 1
    print(f"\n통과. 클래스 {len(CLASSES)} · 관계 {len(RELATIONS)} 전부 확인했습니다")
    print(f"IOF 밖에서 가져온 것 클래스 {len(EXT_CLASSES)} · 관계 {len(EXT_RELATIONS)}"
          f"  ⚠️ 대조하지 않는다. 출처는 {' · '.join(EXT_SOURCE)}")
    return 0


def export() -> int:
    rc = check()
    if rc:
        print("\n검사가 실패해 내보내지 않았습니다")
        return rc
    d = declared()

    def iri(local):
        return None if local is None else IOF_BASE + local

    spec = {
        "이름": "제조 정비 AI 공통 스키마",
        "판": VERSION,
        "상태": "검수 전 초안",
        "근거 문서": "docs/연구/제조-공통스키마.md",
        "표준": {
            "IOF": {"기준": IOF_BASE, "maintenance 배포": MAINTENANCE_RELEASE,
                    "라이선스": "MIT"},
            "MaintIE": {"용도": "상태·조치 어휘와 유형 체계", "라이선스": "MIT"},
            "functionClass": FUNCTION_CLASS,
        },
        "클래스": [
            {"이름": n, "갈래": g, "IOF": iri(l), "모듈": d.get(l), "설명": s or None}
            for n, l, g, s in CLASSES
        ],
        "관계": [
            {"이름": n, "IOF": iri(l), "모듈": d.get(l),
             "출발": a, "도착": b, "조건": c or None,
             "속성": REL_ATTRS.get(n, [])}
            for n, l, a, b, c in RELATIONS
        ],
        "공통 속성": [
            {"이름": n, "자료형": t, "필수": r, "설명": s}
            for n, t, r, s in COMMON_ATTRS
        ],
        "클래스별 속성": CLASS_ATTRS,
        "IOF 밖에서 가져온 것": {
            "출처": EXT_SOURCE,
            "클래스": [{"이름": n, "출처": src, "그쪽 이름": loc, "갈래": g,
                      "설명": d or None} for n, src, loc, g, d in EXT_CLASSES],
            "관계": [{"이름": n, "출처": src, "그쪽 이름": loc, "출발": a,
                     "도착": b, "설명": d or None}
                    for n, src, loc, a, b, d in EXT_RELATIONS],
            "주의": "IOF 배포판에 없으므로 check 가 대조하지 않는다",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"저장 {OUT}  ({OUT.stat().st_size:,} 바이트)")
    return 0


def _domrange() -> dict[str, tuple[list[str], list[str]]]:
    """IOF object property 의 domain 과 range 를 읽는다."""
    out: dict[str, tuple[list[str], list[str]]] = {}
    pat = re.compile(r'<owl:ObjectProperty[^>]*rdf:about="&iof-[a-z]+;([A-Za-z0-9_]+)"\s*>'
                     r'(.*?)</owl:ObjectProperty>', re.S)
    res = lambda b, t: re.findall(
        rf'<{t}[^>]*rdf:resource="[^"]*?[;/]([A-Za-z0-9_]+)"', b)
    for f in sorted(IOF_SRC.glob("*.rdf")):
        for m in pat.finditer(f.read_text(encoding="utf-8", errors="replace")):
            name, body = m.group(1), m.group(2)
            if name not in out:
                out[name] = (res(body, "rdfs:domain"), res(body, "rdfs:range"))
    return out


def relations() -> None:
    """우리 관계의 출발·도착을 IOF 의 domain·range 와 나란히 놓는다.

    ⚠️ **자동 판정이 아니다.** BFO 상위 클래스가 대부분이라 기계가 적합성을 판정할
       수 없다. 사람이 눈으로 맞대어 보라고 나란히 찍는다. 이름이 존재하는지만 보던
       검사로는 2026-09-29 에 발견한 세 오류를 잡지 못했다.
    """
    dr = _domrange()
    cls = {n: l for n, l, _, _ in CLASSES}
    print(f"{'우리 관계':<16}{'IOF':<30}{'우리 출발→도착':<26}{'IOF domain→range'}")
    for n, l, a, b, c in RELATIONS:
        if l is None:
            print(f"{n:<16}{'(신설)':<30}{a+'→'+b:<26}—")
            continue
        d, r = dr.get(l, ([], []))
        ours = f"{cls.get(a) or a}→{cls.get(b) or b}"
        print(f"{n:<16}{l:<30}{ours:<26}"
              f"{','.join(d) or '—'}→{','.join(r) or '—'}")
    print("\n조건이 붙은 관계")
    for n, l, a, b, c in RELATIONS:
        if c:
            print(f"  {n}: {c}")


def roles() -> int:
    """IOF 의 어느 클래스가 역할로 정의되어 있는지 센다.

    2026-09-30 에 알았다. `PieceOfEquipment` 와 `MaintainableMaterialItem` 은
    계층이 아니라 **같은 물체의 다른 역할**이다. 둘 다
    `(MaterialArtifact ∨ EngineeredSystem) ∧ ∃r(…Role(r) ∧ hasRole(x,r))` 이다.
    그래서 어느 쪽도 다른 쪽을 포함하지 않는다.

    **판정 기준.** 그 클래스의 선언 블록에 `owl:equivalentClass` 가 있고 그 안에
    `hasRole` 제약이 있는 경우만 센다.

    - 필요 조건으로만(`rdfs:subClassOf` 안에) `hasRole` 이 나오는 것은 세지 않는다
    - 역할 클래스 자체(`EquipmentRole` 등)는 세지 않는다. 그것은 역할이지 역할로
      정의된 클래스가 아니다
    - 여러 파일에 같은 이름이 나오면 처음 만난 선언을 쓴다

    ⚠️ **원문이 금지한 것은 「종류」를 그 아래 두는 것이다.** 설명 주석은
    `specific kinds of equipment such as machines, devices, and tools` 를
    `material artifact` 나 `engineered system` 아래에 **선언(assert)**하라고 한다.
    **개체가 그 클래스의 인스턴스가 될 수 없다는 뜻이 아니다.** 동치 정의에 따라
    물질 인공물이면서 설비 역할을 가진 개체는 `PieceOfEquipment` 에 속한다. 이것은
    정의에서 따라오는 귀결이며 우리가 추론기를 돌려 확인한 것은 아니다.
    """
    import re as _re
    d = declared()  # 이름이 실제로 선언되었는지도 함께 본다
    role: set[str] = set()
    for f in sorted(IOF_SRC.glob("*.rdf")):
        s = f.read_text(encoding="utf-8", errors="replace")
        starts = [(m.start(), m.group(1)) for m in
                  _re.finditer(r'<owl:Class rdf:about="&iof-[a-z]+;([A-Za-z0-9_]+)"\s*>', s)]
        for i, (pos, n) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(s)
            blk = s[pos:end]
            if "equivalentClass" in blk and _re.search(r'hasRole"/>', blk):
                role.add(n)
    print(f"IOF 클래스 선언 {len(d)} 개 가운데 역할로 정의된 것 {len(role)} 개\n")
    ours = [(c[0], c[1]) for c in CLASSES if c[1]]
    hit = [(k, v) for k, v in ours if v in role]
    print(f"우리가 쓰는 IOF 클래스 {len(ours)} 개 가운데 역할 정의 {len(hit)} 개")
    for k, v in hit:
        print(f"   {k:18s} {v}")
    print("\n⚠️ 역할 정의 클래스는 분류 계층이 아니다. **종류(하위 클래스)를 그 아래")
    print("   선언하지 않는다.** material artifact 나 engineered system 아래 선언하고")
    print("   역할을 준다. 개체가 그 클래스에 속하는 것은 정의에서 따라오는 귀결이다.")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    sys.exit({"check": check, "export": export, "relations": relations,
              "roles": roles}.get(cmd, check)())
