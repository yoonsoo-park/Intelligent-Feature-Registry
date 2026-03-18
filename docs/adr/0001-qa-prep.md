# ADR-0001 QA Prep: API-First Design 방어 질문 세트

## 핵심 메시지 (일관되게 유지할 것)

1. 원본 ADR Option 2의 **목표에 100% 동의** — governance, usage attribution, policy enforcement
2. ADR 위반이 아니라 **구현 방식 제안** — 로직의 위치를 서버에 두자
3. SDK-Enforced여도 못 막는 건 마찬가지 — **진짜 enforcement는 SAST와 IAM**

---

## Q1: ADR 위반 아닌가?

**질문 (VP of Engineering):**
> "Option 2에 'All consumers must use the Intelligence Platform SDK. Direct Bedrock access outside of the SDK is not permitted'라고 되어있는데, ADR-0001에는 SDK is not required라고 써있습니다. 승인된 ADR 위반 아닌가요?"

**답변 전략:**
- 기존 ADR에서 강하게 주장한 governance, observability 등에 완벽하게 동의
- 이건 구현 방안에 대한 토론이지 ADR의 방향성을 부정하는 것이 아님
- 가장 강조할 부분은 **로직의 위치** — API를 중심으로 server side에 배치
- ADR-0001의 curl 예시는 API 설계가 올바르다는 것을 보여주기 위한 것. 실제 팀들은 SDK를 사용하고 Orca SAST가 enforcement

**주의:** "SDK is not required"라고 ADR에 직접 쓴 부분에 대해 해명 준비 필요

---

## Q2: SDK가 유틸 함수 수준인데 SDK라고 부를 수 있나?

**질문 (Principal Engineer):**
> "SDK에 로직이 없으면 SDK가 하는 일이 뭔가요? SigV4 서명이랑 HTTP 호출 하나? 그건 SDK가 아니라 유틸 함수잖아요."

**답변 전략:**
- SDK의 역할은 개발팀이 쉽고 일관되게 Feature Registry를 사용하는 것
- 그 안에 무슨 로직이 들어가느냐는 구현 선택
- 회사 내에서 다양한 언어를 사용하는 상황에서 SDK에 로직을 넣으면 언어별 포팅 필요
- API 중심이면 TypeScript용 SDK가 10줄 이내로 구현 가능

---

## Q3: YAGNI 아닌가? 존재하지 않는 문제를 해결하려는 거 아닌가?

**질문 (VP of Engineering):**
> "언어 종속을 피하자는 건 이해했는데, 지금 존재하지 않는 문제를 해결하려고 아키텍처를 복잡하게 만드는 거 아닌가요?"

**답변 전략:**
- 회사의 많은 팀이 TypeScript를 사용 중. SDK에 로직을 넣으면 TypeScript 팀들이 사용 불가
- API 중심 설계에서 TypeScript용 SDK 구현은 10줄 이하
- API-first가 오히려 더 단순한 아키텍처. SDK에 로직을 넣는 게 더 복잡함

---

## Q4: SDK 버전 업데이트로 정책을 push할 수 없지 않나?

**질문 (Principal Engineer):**
> "내일 특정 모델 사용을 차단해야 한다면, SDK였으면 새 버전에서 차단 로직 넣고 업데이트 강제하면 됩니다. API-first에서는 어떻게 실시간으로 차단하죠?"

**답변 전략:**
- API 중심이 오히려 더 강력한 차단을 가능하게 함
- 해당 팀에 배정된 inference profile 삭제 = 즉시 차단. 추가 로직 불필요
- Server 측에서도 동일한 정책 구현 가능
- SDK 버전 업데이트는 팀의 협조가 필요하지만, API는 중앙에서 즉시 실행

**역공 포인트:** SDK 업데이트를 100개 팀이 즉시 할까? 배포 주기가 다르면 차단에 며칠~몇 주 소요. inference profile 삭제는 즉시.

---

## Q5: 새로운 정책 추가 (guardrail, rate limiting)은?

**질문 (Principal Engineer):**
> "모든 Bedrock 호출에 특정 guardrail을 적용하거나, rate limiting을 팀별로 다르게 적용해야 한다면? 레지스트리가 프록시가 아니니 런타임 호출에 개입 못하지 않나요?"

**답변 전략:**
- 두 가지 종류의 정책을 구분:
  - **프로필 발급 시점 정책** (guardrail ID 연결, 팀별 quota) — Feature Registry API에서 처리 가능
  - **호출 시점 정책** (매 호출 rate limit) — 프록시가 필요하고, 그건 Option 2가 아니라 **Option 1의 영역**
- guardrail 적용은 inference profile 생성 시에 추가 가능
- 런타임 호출 개입이 필요하면 Option 1으로 돌아가는 것. SDK 방식에서도 마찬가지로 불가능한 부분

**킬러 포인트:** "런타임 호출에 개입하려면 프록시가 필요하고, 그건 Option 2가 아니라 Option 1의 영역입니다."

---

## Q6: SAST는 정적 분석 — 런타임 우회는?

**질문 (Security Lead):**
> "런타임에 환경변수나 config로 raw model ID를 주입하면 SAST가 못 잡죠. 코드에는 `converse(modelId=config.get("model"))`라고만 되어있으면 SAST 통과합니다."

**답변 전략:**
1. **재프레이밍 먼저** — 이건 API-first 고유의 문제가 아니라 Option 2 전체의 트레이드오프. SDK에 로직을 넣어도 boto3 직접 호출은 못 막음. 원본 ADR Cons에도 명시됨
2. **IAM policy로 인프라 레벨 enforcement** — Allow resource를 `application-inference-profile/*` 패턴으로만 설정하면 foundation model ARN 직접 호출은 implicit deny로 차단
3. **SCP/Permission Boundary** — account 레벨에서 foundation model ARN 호출을 전체 차단 가능

**구체적 예시:**
```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel", "bedrock:Converse"],
  "Resource": "arn:aws:bedrock:*:042279143912:application-inference-profile/*"
}
```
- `converse(modelId="anthropic.claude-sonnet-4-20250514")` → **Access Denied**
- `converse(modelId="arn:...application-inference-profile/xyz789")` → **허용**
- 환경변수로 raw model ID 주입해도 IAM이 런타임에서 차단

---

## Q7: 수요가 있나? 실제 사용하는 팀이 있나?

**질문 (Product Owner):**
> "실제로 이 Feature Registry를 쓰려는 팀이 있나요? 아니면 GAP팀만 쓰고 있는 건가요?"

**답변 전략:**
- 현재 GAP팀 내에서 사용 중이고, 운영하면서 겪는 경험을 바탕으로 전사적 방향을 제시하는 단계
- Option 2 ADR이 승인되면 모든 팀이 inference profile을 통해 Bedrock을 사용해야 함. 그때 Feature Registry가 그 경로가 됨
- GAP팀이 먼저 경험하고 있으니 지금 방향을 잡는 것

**주의:** "강제"라는 단어 사용 금지. "바른 방향을 제시"로 프레이밍

---

## Q8: 원본 ADR 문구 수정해야 하나?

**질문 (Principal Engineer):**
> "ADR-0001을 수락하면 원본 ADR Option 2의 'must use SDK' 문구를 어떻게 하자는 건가요?"

**답변 전략:**
- 수정할 필요 없음
- 원본 ADR은 **목표**를 정의 — SDK를 통한 governance, usage attribution, policy enforcement
- ADR-0001은 그 목표를 달성하는 **구현 방식**을 제안
- SDK는 존재하고 팀들은 사용. 다만 SDK 안에 비즈니스 로직을 넣지 않고 서버에 둔다는 차이
- 원본 문구와 충돌하지 않음

---

## Q9: 관리 포인트가 늘어나는 거 아닌가?

**질문 (Principal Engineer):**
> "SDK는 한 리포에서 관리하면 되는데 API-first는 SDK도 관리하고 API 서버도 관리해야 하잖아!"

**답변 전략:**
- Separation of concern에 맞는 방향. SDK는 Feature Registry 활용에만 집중, 모든 안전 로직은 server에서 AWS native를 최대한 활용
- **역공:** SDK에 비즈니스 로직을 넣으면 SDK 하나로 관리하는 게 아님:
  - SDK 새 버전 릴리즈 → 모든 팀에 배포 → 안 하는 팀 추적 → 강제 업데이트
  - 팀마다 다른 버전 = 정책 불일치
  - 진짜 관리 포인트: SDK × 사용하는 팀 수
  - 서버에 로직 두면: 한 번 배포 = 즉시 전체 적용

---

## Q10: SDK가 thin wrapper면 왜 필요한가?

**질문 (반대 방향 공격):**
> "SDK는 그냥 API request wrapping인데 왜 필요해?"

**답변 전략:**
- **DX 통일** — 10개 팀이 각자 HTTP 호출 코드를 짜면 SigV4 서명, 에러 핸들링, 재시도 로직이 10가지 방식으로 생김
- **Orca SAST 연동** — SDK import를 체크하는 것이 임의의 HTTP 호출 분석보다 정확
- **변경 전파** — API URL 변경, 인증 방식 변경 시 SDK만 업데이트하면 됨

핵심 단어: **표준화**. 로직이 아니라 표준화를 위한 SDK.

---

## SDK에 로직을 넣을 때의 문제점 정리

| # | 문제점 | 서버에 로직 두면? |
|---|--------|-----------------|
| 1 | Bedrock API 변경 시 SDK 업데이트 필요 | 서버만 수정 |
| 2 | 로직 복잡 + 언어 종속 | 서버 1개, SDK는 thin wrapper |
| 3 | 팀이 업데이트 안 하면 새 규칙 미적용 | 서버 배포 = 즉시 전체 적용 |
| 4 | 언어별 테스트 부담 | 서버 테스트만 유지 |
| 5 | 버전 파편화로 정책 불일치 | 불가능 |
| 6 | 장애 추적 시 버전 확인 필요 | 서버 로그 한 곳 |
| 7 | 정책 변경마다 배포 순회 | 서버 한 번 배포 |

실전에서는 1, 2, 3을 메인으로 사용. 상대방이 파고들면 4-7을 추가로 제시.

---

## Multi-Account 관련

**질문:**
> "원본 ADR은 multi-account를 가정하고 있는데 API 방식으로 가능한가?"

**답변 전략:**
- Option 3(multi-account)는 **별도 side plan** — quota 격리와 비용 추적 목적
- 원본 ADR: "The central platform provides landing zone setup, guardrails, and inference profiles" → Feature Registry의 역할 그대로
- 배포 전략: account별 Feature Registry 배포 또는 cross-account role assume
- **API-first의 장점:** multi-account 로직이 서버에 있으면 SDK 변경 없음. SDK에 있으면 SDK도 업데이트 필요
- Billing: AWS Organizations consolidated billing + inference profile 태그로 Cost Explorer에서 팀별/기능별 비용 추적. 별도 billing 서비스 불필요

---

## Q11: Inference profile 1,000개 limit에 걸리지 않나?

**질문 (Engineer):**
> "AWS inference profile limit이 account당 region당 1,000개인데, tenant별로 profile을 만들면 200 tenants × 10 models = 2,000개로 초과하지 않나요?"

**답변 전략:**
- 인터널 사용에서는 tenant별 격리가 불필요 — 같은 회사
- inference profile을 **team + feature + model** 단위로 공유하면 limit 문제 해결
- 예: 10 teams × 5 features × 4 models = 200개 (1,000 이하)
- 익스터널(다른 은행)이 필요해지면 multi-account(Option 3)로 account별 1,000개 limit 확보

---

## Q12: 팀이 무한으로 Bedrock을 호출하면 비용 폭발 아닌가?

**질문 (Engineering Manager):**
> "인터널 팀 코드에 버그가 있어서 무한 루프로 Bedrock converse API를 호출하면 천문학적 비용이 나올 텐데, 이걸 어떻게 막나요?"

**답변 전략:**
- Feature Registry는 프록시가 아니라서 런타임 호출을 직접 제어하지 않음
- 대신 **인프라 레이어에서 방어**:
  1. **CloudWatch Alarm 자동 생성** — inference profile 생성 시 호출 수/토큰 사용량 알람 자동 설정
  2. **AWS Bedrock Service Quotas** — account 레벨 TPM/RPM limit
  3. **AWS Budgets** — 태그 기반 예산 설정, 초과 시 알림
  4. **긴급 차단** — inference profile 삭제로 즉시 호출 실패
- 호출 단위 rate limiting이 필요하면 프록시가 필요하고, 그건 Option 1의 영역

---

## Q13: 다른 팀의 profile을 조회/삭제할 수 있지 않나?

**질문 (Security Lead):**
> "인증이 tenant credential 기반인데, tenant를 키에서 뺐으면 아무 팀 profile이나 접근 가능한 거 아닌가요?"

**답변 전략:**
- **현재 (single account, 인터널):** 신뢰 기반. 유효한 nCino credential이 있으면 접근 가능. 인터널이므로 허용 범위
- **미래 (multi-account, 익스터널):** account 격리가 보안 경계. 다른 account의 inference profile은 cross-account 권한 없이 호출/삭제 불가
- inference profile ARN을 아는 것 자체는 보안 위협이 아님 — 호출 권한은 IAM이 제어

---

## 답변 시 주의사항

1. **"~거 같습니다" 사용 금지** → "~입니다"로 확신 있게
2. **"강제" 사용 금지** → "방향을 제시", "ADR 적용 시 필요"
3. **AWS Platform 이야기 금지** — 다른 팀을 적으로 돌릴 필요 없음
4. **상대 질문이 API-first만의 문제인 것처럼 올 때** → "이건 SDK-Enforced여도 동일합니다" 재프레이밍 먼저
5. **표면 질문만 답하지 말고 숨은 의도를 다루기**
6. **구체적 수치/예시 적극 활용** — "10줄", IAM policy JSON 등
