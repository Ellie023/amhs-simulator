# FAB AMHS Simulator

반도체 공장(FAB) 안에서 웨이퍼를 자동으로 옮겨 주는 물류 시스템(AMHS)을 Python으로 구현한 콘솔 시뮬레이터입니다.

> AMHS(Automated Material Handling System) — 반도체 FAB에서 천장 레일을 따라 움직이는 무인 운반 로봇(OHT)이 웨이퍼 박스(FOUP/LOT)를 공정 설비 사이로 자동 운반하는 시스템.

---

## 이 프로젝트가 다루는 핵심 문제

반도체 공장에는 수백 개의 공정 설비가 있고, 수천 개의 웨이퍼 박스가 정해진 순서대로 설비를 거쳐야 합니다. 이때 세 가지 문제를 풀어야 합니다.

1. **어떤 경로로 이동할 것인가** — 설비 간 이동 거리가 다르므로 최단 경로를 계산해야 한다
2. **어떤 로봇을 배차할 것인가** — 여러 운반 로봇 중 지금 당장 가장 효율적인 로봇을 골라야 한다
3. **로봇이 고장났을 때 어떻게 할 것인가** — 운반 도중 고장 발생 시 다른 로봇이 즉시 대신해야 한다

이 시뮬레이터는 위 세 문제에 대한 알고리즘을 코드로 구현하고, 실제처럼 시간이 흐르는 환경에서 검증합니다.

---

## 시뮬레이션 구조

```
공장 레이아웃 (OHT 레일망)

 LOAD_PORT                         ← 웨이퍼가 투입되는 입구
     │
  BUFFER_A ──── ETCH-01            ← 식각(Etching) 설비
     │       └── ETCH-02
  BUFFER_B ──── PHOTO-01           ← 노광(Photolithography) 설비
     │       └── PHOTO-02
  BUFFER_C ──── CMP-01             ← 평탄화(CMP) 설비
     │       └── CMP-02
 UNLOAD_PORT                       ← 완료된 웨이퍼가 나가는 출구
```

각 **LOT(웨이퍼 박스)**은 반드시 `ETCH → PHOTO → CMP` 순서로 공정을 거쳐야 하며, OHT(천장 레일 로봇)가 LOT을 다음 설비까지 운반합니다.

| 구성 요소 | 수량 | 설명 |
|---|---|---|
| 공정 설비 | 6대 | ETCH-01/02, PHOTO-01/02, CMP-01/02 |
| OHT (운반 로봇) | 3대 | OHT-01, OHT-02, OHT-03 |
| LOT (웨이퍼 박스) | 3개 | LOT-1001, LOT-1002, LOT-1003 |

---

## 실행 방법

Python 3.8 이상이면 별도 설치 없이 실행 가능합니다.

```bash
# 기본 실행
python main.py

# 옵션
python main.py --seed 7          # 랜덤 시드 변경 (결과 재현용)
python main.py --failover 0.05   # OHT 고장 확률 조정 (기본값: 12%)
python main.py --verbose         # 매 tick의 상세 이벤트 로그 출력
python main.py --maxticks 500    # 최대 시뮬레이션 시간 제한
```

### 출력 예시 (seed=42, failover=12%)

```
[LOT Summary]
  LOT ID       Total Time  Wait Ticks  Status
  LOT-1001             52           5  COMPLETE
  LOT-1002             72           8  COMPLETE
  LOT-1003            113          34  COMPLETE   ← ETCH-01/PHOTO-01/CMP-01 경합 대기

  Average wait ticks per LOT : 15.67

[OHT Summary]
  OHT ID    Tasks  Total Dist  Final Pos   Status
  OHT-01        1         4.0  ETCH-02     Idle
  OHT-02        3        29.0  ETCH-01     Idle
  OHT-03        5        44.0  CMP-01      Idle

[Failover Events] (total=22)
  tick=  1 | OHT-02 ERROR | LOT-1002 (LOAD_PORT->ETCH-02) | reassigned->OHT-03
  tick=  4 | OHT-01 ERROR | LOT-1001 (LOAD_PORT->ETCH-01) | reassigned->PENDING
  tick=  7 | OHT-03 ERROR | LOT-1002 (LOAD_PORT->ETCH-02) | reassigned->OHT-01
  ...
```

LOT-1003의 대기 시간(34 ticks)이 긴 이유는 LOT-1001과 같은 설비 라인(ETCH-01 → PHOTO-01 → CMP-01)을 공유해 매 공정마다 설비가 빌 때까지 기다리기 때문입니다.

---

## 파일 구조

```
amhs_simulator/
├── src/
│   ├── models.py      # 데이터 정의 — Equipment, OHT, Lot, FailoverEvent
│   ├── graph.py       # 공장 지도(그래프) + Dijkstra 최단 경로
│   ├── scheduler.py   # OHT 배차 + 고장 처리
│   └── simulator.py   # 시간 흐름 제어, 공정 처리, 결과 출력
└── main.py            # 실행 진입점 (옵션 파싱)
```

---

## 구현 알고리즘

### 1. 최단 경로 탐색 — Dijkstra

공장 레일망을 그래프(노드 = 설비/버퍼, 엣지 = 레일 구간 거리)로 모델링합니다.  
OHT가 어디로 이동해야 하는지 결정할 때마다 **Dijkstra 알고리즘**으로 최단 경로를 계산합니다.

```
예시: OHT-01이 ETCH-01에 있고 CMP-01로 가야 한다면

ETCH-01 → BUFFER_A → BUFFER_B → BUFFER_C → CMP-01
거리:  1.5  +  3.0  +  3.0  +  1.5  =  9.0
```

구현은 **우선순위 큐(heapq)**를 사용해 "지금까지 발견한 경로 중 가장 짧은 것"을 먼저 탐색하는 방식으로 동작합니다.  
노드 수 V, 엣지 수 E일 때 시간복잡도는 **O((V + E) log V)** 입니다.

```python
heap = [(0.0, source)]
while heap:
    d, u = heapq.heappop(heap)          # 가장 짧은 경로 꺼내기
    for v, w in self._adj[u]:
        if d + w < dist[v]:
            dist[v] = d + w
            heapq.heappush(heap, (dist[v], v))
```

---

### 2. OHT 배차 — Nearest Dispatching

LOT을 운반해야 할 때 "지금 당장 출발할 수 있는(Idle) OHT 중 LOT과 가장 가까운 것"을 선택합니다.  
가까운 OHT를 고르면 픽업 이동 거리가 줄어 전체 대기 시간이 단축됩니다.

```
LOT 운반 요청 발생 (A 설비 → B 설비)
        │
        ▼
Idle 상태의 OHT 목록 조회
        │
        ▼
각 OHT의 현재 위치에서 A까지의 거리를 Dijkstra로 계산
        │
        ▼
거리가 가장 짧은 OHT 선택 → 배차
        │
        ▼
Idle OHT가 없으면 → 대기 큐에 등록, 매 tick 자동 재시도
```

---

### 3. 고장 처리 — Failover

매 시간 단위(tick)마다 운반 중인 OHT에 설정된 확률로 고장이 발생합니다.  
고장 시 시스템은 세 가지를 즉시 처리합니다.

```
OHT 고장 발생
        │
        ├─ 고장 OHT: 3 tick 동안 ERROR 상태 유지 (배차 대상에서 제외)
        │
        ├─ 운반 중이던 LOT: 출발지에서 다시 대기
        │
        └─ 고장 OHT를 제외한 가장 가까운 Idle OHT에 즉시 재배차
```

고장 OHT를 즉시 복구시키지 않고 일정 시간 **ERROR 상태를 유지**하는 이유는, 복구 직후 같은 OHT가 다시 배차되는 것을 막기 위해서입니다. 실제 장비 수리에 걸리는 시간(MTTR)을 단순하게 모델링한 것입니다.

---

### 4. 설비 점유 및 대기 큐

각 설비는 한 번에 하나의 LOT만 처리할 수 있습니다. 목적 설비가 이미 사용 중이면 LOT은 설비별 **대기 큐**에 줄을 섭니다.

```
설비 A가 LOT-1001 처리 중일 때 LOT-1003도 설비 A로 가야 하면:

LOT-1003 → equip_queue[A] 에 등록 → WAITING 상태로 대기

LOT-1001 처리 완료 → 설비 A 해제 → LOT-1003 자동으로 배차 시작
```

이 구조 덕분에 LOT-1001과 LOT-1003이 같은 라인(ETCH-01 → PHOTO-01 → CMP-01)을 공유할 때 실제와 같이 대기 시간이 발생하고, 설비 병목이 전체 처리 시간에 미치는 영향을 수치로 확인할 수 있습니다.

---

### 5. Tick 기반 시뮬레이션

"시간이 흐른다"는 것을 **tick(시간 단위)**으로 표현합니다. 매 tick마다 아래 순서로 상태가 갱신됩니다.

```
tick 1 → tick 2 → tick 3 → ...

각 tick에서:
  1. 모든 OHT: 이동 진행 1 tick, 고장 여부 판정
  2. 방금 목적지에 도착한 LOT: 공정 시작
  3. 공정 중인 LOT: 남은 시간 1 tick 차감, 완료 시 다음 공정 요청
  4. 모든 LOT 완료 여부 확인 → 완료면 종료
```

tick이 정수이므로 이동 거리(소수)는 반올림해 tick 수로 변환됩니다. `--seed` 옵션으로 난수 시드를 고정하면 동일한 시뮬레이션을 재현할 수 있습니다.

---

## 설계 방향

- **외부 라이브러리 없음** — `heapq`, `dataclasses`, `random`, `logging` 표준 모듈만 사용
- **레이어 분리** — 데이터 정의(models) / 경로 탐색(graph) / 배차·고장처리(scheduler) / 시간 흐름(simulator) 를 독립적으로 분리해 각 역할을 명확히 구분
- **재현 가능한 실험** — `random.Random(seed)` 로 동일 시드에서 항상 같은 결과 보장
- **관찰 가능성** — `logging` 으로 모든 이벤트(배차, 도착, 고장, 재배차)를 레벨별 기록
